"""Worker process.

* ``WORKFLOW_BACKEND=local``     — scheduler loop + durable local workflow runner.
* ``WORKFLOW_BACKEND=temporal``  — Temporal worker (production stages as activities).
* ``--render-only``              — only the Remotion render queue (installations where rendering
  must not happen inside the API process; pair with ``RENDER_IN_API=false``).

The API process renders by default (``RENDER_IN_API=true``), so a single-process deployment renders
without extra setup. When both run, each claims queued jobs from the database; a render job has one
owner because it is claimed by a guarded status transition.

Run:  python -m app.worker [--render-only]
"""

from __future__ import annotations

import argparse
import asyncio
import signal

from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings

log = get_logger("factory.worker")


def _install_signal_handlers(stop: asyncio.Event) -> None:
    def _stop(*_: object) -> None:
        log.info("shutdown signal received")
        stop.set()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _stop)
            except NotImplementedError:  # Windows event loop
                signal.signal(sig, _stop)
    except Exception:  # noqa: BLE001
        pass


async def render_loop(stop: asyncio.Event) -> None:
    """Remotion render queue (recovery + workers)."""
    from app.services.render import render_service

    service = render_service()
    await service.start()
    await stop.wait()
    await service.shutdown()


async def render_only() -> None:
    from app.db.session import engine, init_models
    from app.services.render import render_service

    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        await init_models()  # development convenience; production uses `alembic upgrade head`
    await render_service().reconcile_schema()
    stop = asyncio.Event()
    _install_signal_handlers(stop)
    log.info("render worker started · concurrency %s", settings.render_concurrency)
    await render_loop(stop)
    await engine.dispose()
    log.info("render worker stopped")


async def local_loop() -> None:
    from app.db.session import engine, init_models
    from app.services.render import render_service
    from app.workflow.pipeline import runner
    from app.workflow.scheduler import expire_approvals, scheduler_tick

    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        await init_models()  # development convenience; production uses `alembic upgrade head`
    else:
        await render_service().reconcile_schema()
    stop = asyncio.Event()
    _install_signal_handlers(stop)

    # Render here too unless the API already owns the queue (RENDER_IN_API=true).
    if not settings.render_in_api:
        await render_service().start()
        log.info("render queue started in worker")

    db = settings.database_url.rsplit("/", 1)[-1].split("?")[0]
    log.info("local worker started · poll %ss · scheduler %s · db %s",
             settings.scheduler_poll_seconds, settings.scheduler_enabled, db)
    # Readiness marker for container healthchecks (the worker exposes no HTTP port).
    from pathlib import Path

    ready = Path("/tmp/factory-worker-ready")
    try:
        await asyncio.to_thread(ready.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(ready.touch)
    except OSError:
        log.debug("worker readiness marker unavailable on this platform")
    while not stop.is_set():
        try:
            if settings.scheduler_enabled:
                await scheduler_tick()
            from app.db.session import session_scope

            async with session_scope() as session:
                await expire_approvals(session)
        except Exception:  # noqa: BLE001
            log.exception("worker tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.scheduler_poll_seconds)
        except TimeoutError:
            pass
    if not settings.render_in_api:
        await render_service().shutdown()
    await runner.shutdown()
    await engine.dispose()
    log.info("local worker stopped")


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="factory-worker")
    parser.add_argument("--render-only", action="store_true",
                        help="only run the Remotion render queue (no scheduler, no workflows)")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.debug)
    if args.render_only:
        await render_only()
        return
    if settings.workflow_backend == "temporal":
        from app.workflow.temporal_adapter import run_worker

        await run_worker()
        return
    await local_loop()


if __name__ == "__main__":
    asyncio.run(main())
