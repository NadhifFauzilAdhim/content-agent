"""Declarative base and shared column mixins."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator, Uuid

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class JSONB(TypeDecorator):
    """JSON that uses PostgreSQL JSONB when available, generic JSON elsewhere (SQLite tests)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:  # pragma: no cover - dialect branch
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB as PGJSONB

            return dialect.type_descriptor(PGJSONB())
        return dialect.type_descriptor(JSON())


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime | None) -> datetime | None:
    """Normalise a stored timestamp to UTC-aware.

    SQLite (and some drivers) return naive datetimes even for ``DateTime(timezone=True)``
    columns; subtracting one from ``datetime.now(UTC)`` raises. Always route timestamp
    arithmetic through this helper.
    """
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def elapsed_seconds(start: datetime | None, end: datetime | None = None) -> float:
    end = aware(end) or utcnow()
    start = aware(start)
    return 0.0 if start is None else (end - start).total_seconds()


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        dict: JSONB,
        dict[str, Any]: JSONB,
        list: JSONB,
        list[str]: JSONB,
        list[dict[str, Any]]: JSONB,
    }


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
