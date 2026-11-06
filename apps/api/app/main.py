"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings

logger = get_logger("factory.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.debug)
    background: list[asyncio.Task] = []

    from app.db.session import engine, init_models

    if settings.database_url.startswith("sqlite"):
        # Local development / tests: create schema and seed the workspace on first boot.
        await init_models()
        from app.cli import bootstrap

        await bootstrap(if_empty=True)

    if settings.workflow_backend == "local" and settings.scheduler_enabled:
        from app.workflow.scheduler import scheduler_tick

        async def _scheduler_loop() -> None:
            while True:
                try:
                    await scheduler_tick()
                except Exception:  # noqa: BLE001 - a tick must never kill the loop
                    logger.exception("scheduler tick failed")
                await asyncio.sleep(settings.scheduler_poll_seconds)

        background.append(asyncio.create_task(_scheduler_loop()))

    # Video rendering is CPU-heavy. `RENDER_IN_API=true` (default) runs the render queue in this
    # process so a single-process deployment renders without extra setup; set it to false when a
    # dedicated render worker (`python -m app.worker --render-only`) owns the queue instead.
    from app.services.render import render_service

    renderer_service = render_service()
    if settings.render_in_api:
        await renderer_service.start()  # reconcile schema, recover interrupted jobs, run the queue

    logger.info("api.start environment=%s workflow=%s", settings.environment, settings.workflow_backend)
    try:
        yield
    finally:
        for task in background:
            task.cancel()
        if background:
            await asyncio.gather(*background, return_exceptions=True)
        if settings.render_in_api:
            await renderer_service.shutdown()

        from app.workflow.pipeline import runner

        await runner.shutdown()
        await engine.dispose()
        logger.info("api.stop")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Factory API",
        version="0.1.0",
        description="Autonomous AI YouTube Content Factory",
        docs_url="/docs" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request payload is invalid",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(exc.detail)}},
        )

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
