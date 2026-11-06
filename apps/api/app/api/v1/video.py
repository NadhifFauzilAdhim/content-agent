"""Video engine API — Remotion render jobs, previews, templates and output validation.

Rendering never happens inside a request: `POST /renders` records a job and returns immediately;
the background worker in `app.services.render` runs `renderMedia()` and streams progress into the
job row, which the dashboard polls.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_principal, require_role, write_audit
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.db.base import aware
from app.db.session import get_session
from app.models import Channel, ContentProject, RenderJob, RenderValidation
from app.services import render as render_svc
from app.services.storyboard import TEMPLATES, TRANSITIONS, template_for

router = APIRouter(prefix="/video", tags=["video"])


class RenderIn(BaseModel):
    template: str | None = Field(default=None, max_length=48)
    kind: Literal["full", "scene", "preview"] = "full"
    scene_indexes: list[int] = Field(default_factory=list, max_length=60)
    fps: int = Field(default=30, ge=12, le=60)
    include_intro: bool | None = None
    include_outro: bool | None = None
    idempotency_key: str | None = Field(default=None, max_length=120)
    wait: bool = False  # only for previews: short jobs may be awaited inline


class RenderOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: str
    template: str
    composition_id: str
    status: str
    stage: str
    progress: int
    width: int
    height: int
    fps: int
    duration_s: float
    rendered_frames: int
    bytes: int | None
    output_url: str | None
    poster_url: str | None
    error_code: str | None
    error_message: str | None
    attempts: int
    max_attempts: int
    scene_indexes: list[int]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def _url(key: str | None) -> str | None:
    return f"/files/{key}" if key else None


def _out(job: RenderJob) -> RenderOut:
    return RenderOut(
        id=job.id,
        project_id=job.project_id,
        kind=job.kind,
        template=job.template_id,
        composition_id=job.composition_id,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        width=job.width,
        height=job.height,
        fps=job.fps,
        duration_s=round(float(job.duration_s or 0), 2),
        rendered_frames=job.rendered_frames,
        bytes=job.bytes,
        output_url=_url(job.output_key),
        poster_url=_url(job.poster_key),
        error_code=job.error_code,
        error_message=job.error_message,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        scene_indexes=list(job.scene_indexes or []),
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


async def _project(
    session: AsyncSession, principal: Principal, project_id: uuid.UUID
) -> ContentProject:
    project = await session.get(ContentProject, project_id)
    if project is None or project.workspace_id != principal.workspace.id:
        raise NotFoundError("Project not found")
    return project


async def _job(session: AsyncSession, principal: Principal, job_id: uuid.UUID) -> RenderJob:
    job = await session.get(RenderJob, job_id)
    if job is None or job.workspace_id != principal.workspace.id:
        raise NotFoundError("Render not found")
    return job


# --------------------------------------------------------------------------- engine


@router.get("/engine")
async def engine(
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    """Remotion engine status: Node runtime, package versions, bundle availability."""
    status = await asyncio.to_thread(render_svc.engine_status)
    return {
        **status,
        "templates": [
            {"id": tid, "label": meta["label"], "formats": list(meta["formats"]),
             "width": meta["width"], "height": meta["height"]}
            for tid, meta in TEMPLATES.items()
        ],
        "transitions": list(TRANSITIONS),
    }


@router.get("/templates")
async def templates(
    principal: Principal = Depends(get_principal),
) -> list[dict[str, Any]]:
    return [
        {"id": tid, **{k: v for k, v in meta.items() if k in ("label", "accent", "background", "ink")},
         "formats": list(meta["formats"]), "width": meta["width"], "height": meta["height"],
         "transition": meta["transition"]}
        for tid, meta in TEMPLATES.items()
    ]


# --------------------------------------------------------------------------- jobs


@router.post("/projects/{project_id}/renders", response_model=RenderOut, status_code=202)
async def create_render(
    project_id: uuid.UUID,
    payload: RenderIn,
    request: Request,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> RenderOut:
    project = await _project(session, principal, project_id)
    channel = await session.get(Channel, project.channel_id)
    template = template_for(channel.video_format if channel else "16:9", payload.template)
    if payload.template and payload.template not in TEMPLATES:
        raise ValidationAppError(
            f"Unknown template '{payload.template}'. Available: {', '.join(TEMPLATES)}"
        )
    if payload.kind == "scene" and not payload.scene_indexes:
        raise ValidationAppError("A scene render needs at least one scene index")
    result = await render_svc.render_service().enqueue(
        session,
        project=project,
        template_id=template,
        kind=payload.kind,
        scene_indexes=payload.scene_indexes or None,
        requested_by=principal.user.id,
        fps=payload.fps,
        include_intro=payload.include_intro,
        include_outro=payload.include_outro,
        idempotency_key=payload.idempotency_key,
        channel=channel,
    )
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="render.queued" if not result.reused else "render.deduplicated",
                      target_type="render_job", target_id=str(result.job.id), request=request,
                      template=result.job.template_id, kind=result.job.kind)
    await session.commit()
    return _out(result.job)


@router.get("/projects/{project_id}/renders", response_model=list[RenderOut])
async def list_renders(
    project_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[RenderOut]:
    await _project(session, principal, project_id)
    rows = (
        await session.execute(
            select(RenderJob)
            .where(RenderJob.project_id == project_id)
            .order_by(desc(RenderJob.created_at))
            .limit(limit)
        )
    ).scalars()
    return [_out(j) for j in rows]


@router.get("/renders/{job_id}", response_model=RenderOut)
async def get_render(
    job_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> RenderOut:
    return _out(await _job(session, principal, job_id))


@router.get("/renders/{job_id}/status")
async def render_status(
    job_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    job = await _job(session, principal, job_id)
    eta = None
    if job.started_at and 0 < job.progress < 100 and job.status not in ("failed", "cancelled"):
        started = aware(job.started_at)
        elapsed = (datetime.now(UTC) - started).total_seconds() if started else None
        eta = round(elapsed * (100 - job.progress) / max(1, job.progress), 1)
    return {
        "id": str(job.id),
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "rendered_frames": job.rendered_frames,
        "frames": job.frames,
        "eta_seconds": eta,
        "attempts": job.attempts,
        "error": job.error_message,
    }


@router.post("/renders/{job_id}/cancel", response_model=RenderOut)
async def cancel_render(
    job_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> RenderOut:
    job = await _job(session, principal, job_id)
    job = await render_svc.render_service().cancel(session, job)
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="render.cancelled", target_type="render_job", target_id=str(job.id),
                      request=request)
    await session.commit()
    return _out(job)


@router.post("/renders/{job_id}/retry", response_model=RenderOut, status_code=202)
async def retry_render(
    job_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> RenderOut:
    job = await _job(session, principal, job_id)
    if job.status not in ("failed", "cancelled"):
        raise ConflictError(f"Only failed or cancelled renders can be retried (status: {job.status})")
    if job.attempts >= 5:
        raise ConflictError("This render was retried too many times; fix the cause first")
    project = await _project(session, principal, job.project_id)
    channel = await session.get(Channel, project.channel_id)
    result = await render_svc.render_service().enqueue(
        session,
        project=project,
        template_id=job.template_id,
        kind=job.kind,
        scene_indexes=list(job.scene_indexes or []) or None,
        requested_by=principal.user.id,
        fps=job.fps,
        channel=channel,
    )
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="render.retried", target_type="render_job",
                      target_id=str(result.job.id), request=request, previous=str(job.id))
    await session.commit()
    return _out(result.job)


@router.get("/renders/{job_id}/spec")
async def render_spec(
    job_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The exact storyboard snapshot sent to Remotion — same props the Player preview uses."""
    job = await _job(session, principal, job_id)
    return {
        "compositionId": job.composition_id,
        "width": job.width,
        "height": job.height,
        "fps": job.fps,
        "duration_s": job.duration_s,
        "spec": job.spec,
    }


@router.get("/renders/{job_id}/validation")
async def render_validation(
    job_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _job(session, principal, job_id)
    row = await session.scalar(
        select(RenderValidation)
        .where(RenderValidation.job_id == job_id)
        .order_by(desc(RenderValidation.created_at))
    )
    if row is None:
        return {"available": False}
    return {
        "available": True,
        "passed": row.passed,
        "checks": row.checks,
        "issues": row.issues,
        "video_codec": row.video_codec,
        "audio_codec": row.audio_codec,
        "width": row.width,
        "height": row.height,
        "fps": row.fps,
        "duration_s": row.duration_s,
        "bitrate_kbps": row.bitrate_kbps,
        "checked_at": row.created_at,
    }


@router.get("/summary")
async def video_summary(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rows = list(
        (
            await session.execute(
                select(RenderJob.status, func.count(RenderJob.id))
                .where(RenderJob.workspace_id == principal.workspace.id)
                .group_by(RenderJob.status)
            )
        ).all()
    )
    return {
        "engine": await asyncio.to_thread(render_svc.engine_status),
        "by_status": {status: int(count) for status, count in rows},
    }


__all__ = ["router"]
