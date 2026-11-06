"""Async SQLAlchemy engine and session management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.settings import get_settings
from app.db.base import Base

_settings = get_settings()

_is_sqlite = _settings.database_url.startswith("sqlite")

_connect_args = {"check_same_thread": False} if _is_sqlite else {}


def _async_engine():
    engine = create_async_engine(
        _settings.database_url,
        echo=False,
        future=True,
        pool_pre_ping=not _is_sqlite,
        poolclass=NullPool if _is_sqlite else None,
        connect_args=_connect_args,
    )
    if _is_sqlite:
        # SQLite ignores ON DELETE SET NULL / CASCADE unless foreign keys are enabled per connection.
        from sqlalchemy import event

        sync_engine = engine.sync_engine

        @event.listens_for(sync_engine, "connect")
        def _sqlite_fk_hook(dbapi_connection, _record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


class _PerLoopPool:
    """One engine (and session factory) per running event loop.

    Async engine pools are bound to the loop that created them. A process normally has a single
    loop, but tests and embedding scenarios may run two (for example a uvicorn server in a thread
    next to a TestClient). Keying on the loop makes both work without leaking connections.
    """

    def __init__(self) -> None:
        self._engines: dict[int, Any] = {}
        self._factories: dict[int, async_sessionmaker[AsyncSession]] = {}

    def _key(self) -> int | None:
        try:
            import asyncio

            return id(asyncio.get_running_loop())
        except RuntimeError:
            return None

    def engine(self, loop_key: int | None = None):
        key = loop_key if loop_key is not None else self._key()
        if key is None:
            key = -1  # no running loop (import time): a single shared engine
        if key not in self._engines:
            self._engines[key] = _async_engine()
            self._factories[key] = async_sessionmaker(
                self._engines[key], expire_on_commit=False, class_=AsyncSession
            )
        return self._engines[key]

    def session_factory(self, loop_key: int | None = None) -> async_sessionmaker[AsyncSession]:
        self.engine(loop_key)
        key = loop_key if loop_key is not None else self._key()
        return self._factories[key if key is not None else -1]

    async def dispose(self, loop_key: int | None = None) -> None:
        key = loop_key if loop_key is not None else self._key()
        key = key if key is not None else -1
        engine = self._engines.pop(key, None)
        self._factories.pop(key, None)
        if engine is not None:
            await engine.dispose()

    @property
    def current(self):
        return self.engine()

    @property
    def current_factory(self) -> async_sessionmaker[AsyncSession]:
        return self.session_factory()


_engines = _PerLoopPool()


class _EngineProxy:
    """``engine`` for compatibility: forwards to the pool of the current loop."""

    def __getattr__(self, name: str):
        return getattr(_engines.current, name)

    async def dispose(self) -> None:
        await _engines.dispose()


engine = _EngineProxy()


class _SessionFactoryProxy:
    def __call__(self, *args, **kwargs) -> AsyncSession:
        return _engines.current_factory(*args, **kwargs)

SessionFactory = _SessionFactoryProxy()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def engine_scope() -> AsyncIterator[None]:
    """Dispose only this event loop's engine on exit (used by embedded servers and tests)."""
    try:
        yield
    finally:
        await _engines.dispose()


async def init_models() -> None:
    """Create tables directly (development / tests only — production uses Alembic)."""
    from app import models  # noqa: F401  (register metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if _is_sqlite:
            # Local databases evolve with the code; create_all never adds columns to existing
            # tables, so reconcile additive changes here (never destructive).
            from app.db.reconcile import reconcile

            await conn.run_sync(reconcile)
