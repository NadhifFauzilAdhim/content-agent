"""Workflow monitor: list, start, detail, retry, cancel, logs and control."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_principal, require_role, write_audit
from app.core.errors import ConflictError, NotFoundError, WorkflowStateError
from app.db.session import get_session
from app.models import Channel, ContentProject, ProductionWorkflow, WorkflowLog, WorkflowTask
from app.schemas import (
    WorkflowDetailOut,
    WorkflowLogOut,
    WorkflowOut,
    WorkflowTaskOut,
)
from app.workflow.pipeline import STAGE_AGENT, runner

router = APIRouter(prefix="/workflows", tags=["workflows"])

TERMINAL = {"published", "failed", "cancelled"}


def _out(w: ProductionWorkflow, channel_name: str, project_title: str | None) -> WorkflowOut:
    return WorkflowOut(
        id=w.id,
        workflow_key=w.workflow_key,
        channel_id=w.channel_id,
        channel_name=channel_name,
        project_id=w.project_id,
        project_title=project_title,
        trigger=w.trigger,
        status=w.status,
        stage=w.stage,
        current_agent_key=w.current_agent_key or STAGE_AGENT.get(w.stage),
        progress=w.progress,
        retry_count=w.retry_count,
        cost_usd=float(w.cost_usd or 0),
        error_message=w.error_message,
        started_at=w.started_at,
        completed_at=w.completed_at,
        created_at=w.created_at,
    )


async def _names(session: AsyncSession, workflow: ProductionWorkflow) -> tuple[str, str | None]:
    channel = await session.get(Channel, workflow.channel_id)
    project = await session.get(ContentProject, workflow.project_id) if workflow.project_id else None
    return (channel.name if channel else "—"), (project.title if project else None)


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(
    status: str | None = None,
    channel_id: uuid.UUID | None = None,
    limit: int = 50,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[WorkflowOut]:
    query = (
        select(ProductionWorkflow)
        .where(ProductionWorkflow.workspace_id == principal.workspace.id)
        .order_by(ProductionWorkflow.created_at.desc())
        .limit(min(limit, 200))
    )
    if status:
        query = query.where(ProductionWorkflow.status == status)
    if channel_id:
        query = query.where(ProductionWorkflow.channel_id == channel_id)
    rows = list((await session.execute(query)).scalars())
    out = []
    for w in rows:
        name, title = await _names(session, w)
        out.append(_out(w, name, title))
    return out


@router.post("", response_model=WorkflowOut, status_code=201)
async def start_workflow(
    channel_id: uuid.UUID,
    request: Request,
    force_approval: bool = False,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> WorkflowOut:
    channel = await session.scalar(
        select(Channel).where(
            Channel.id == channel_id,
            Channel.workspace_id == principal.workspace.id,
            Channel.deleted_at.is_(None),
        )
    )
    if channel is None:
        raise NotFoundError("Channel not found")
    from app.workflow.pipeline import WorkflowRepository

    repo = WorkflowRepository(session)
    workflow = await repo.create(
        workspace_id=principal.workspace.id,
        channel_id=channel.id,
        trigger="manual",
        force_approval=force_approval,
    )
    await repo.log(workflow.id, f"Manual production queued by {principal.user.name}")
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="workflow.started", target_type="workflow", target_id=str(workflow.id),
                      request=request, channel_id=str(channel.id))
    await session.commit()
    runner.submit(workflow.id)
    return _out(workflow, channel.name, None)


@router.get("/{workflow_id}", response_model=WorkflowDetailOut)
async def workflow_detail(
    workflow_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> WorkflowDetailOut:
    w = await session.scalar(
        select(ProductionWorkflow).where(
            ProductionWorkflow.id == workflow_id,
            ProductionWorkflow.workspace_id == principal.workspace.id,
        )
    )
    if w is None:
        raise NotFoundError("Workflow not found")
    tasks = list(
        (
            await session.execute(
                select(WorkflowTask)
                .where(WorkflowTask.workflow_id == w.id)
                .order_by(WorkflowTask.step_index, WorkflowTask.attempt)
            )
        ).scalars()
    )
    logs = list(
        (
            await session.execute(
                select(WorkflowLog).where(WorkflowLog.workflow_id == w.id).order_by(WorkflowLog.at)
            )
        ).scalars()
    )
    name, title = await _names(session, w)
    base = _out(w, name, title)
    return WorkflowDetailOut(
        **base.model_dump(),
        tasks=[WorkflowTaskOut.model_validate(t) for t in tasks],
        logs=[
            WorkflowLogOut(id=entry.id, level=entry.level, message=entry.message,
                           context=dict(entry.context or {}), at=entry.at)
            for entry in logs
        ],
        input=dict(w.input_json or {}),
    )


@router.post("/{workflow_id}/retry", response_model=WorkflowOut)
async def retry_workflow(
    workflow_id: uuid.UUID,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> WorkflowOut:
    w = await session.scalar(
        select(ProductionWorkflow).where(
            ProductionWorkflow.id == workflow_id,
            ProductionWorkflow.workspace_id == principal.workspace.id,
        )
    )
    if w is None:
        raise NotFoundError("Workflow not found")
    # A run can also be stranded mid-stage when the process running it stopped (deploy, crash,
    # restart). Those are recoverable: the pipeline is idempotent per stage and resumes from the
    # first incomplete step. Cancelled and finished runs stay terminal — start a new run instead.
    from app.workflow.pipeline import runner as _runner

    stranded = (
        w.status not in ("failed", "pending", "cancelled", "awaiting_approval", "published")
        and not _runner.is_running(w.id)
    )
    if w.status not in ("failed", "pending") and not stranded:
        raise WorkflowStateError(f"Cannot retry a workflow in status '{w.status}'")
    if w.retry_count >= w.max_retries:
        raise WorkflowStateError("Retry limit reached for this workflow")
    w.retry_count += 1
    w.status = "pending"
    w.error_message = None
    w.completed_at = None
    from app.workflow.pipeline import WorkflowRepository

    reason = "Resuming a run that stopped mid-stage" if stranded else "Retry requested"
    await WorkflowRepository(session).log(w.id, f"{reason} (attempt {w.retry_count})")
    await session.commit()
    runner.submit(w.id)
    name, title = await _names(session, w)
    return _out(w, name, title)


@router.post("/{workflow_id}/cancel", response_model=WorkflowOut)
async def cancel_workflow(
    workflow_id: uuid.UUID,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> WorkflowOut:
    w = await session.scalar(
        select(ProductionWorkflow).where(
            ProductionWorkflow.id == workflow_id,
            ProductionWorkflow.workspace_id == principal.workspace.id,
        )
    )
    if w is None:
        raise NotFoundError("Workflow not found")
    if w.status in TERMINAL:
        raise ConflictError(f"Workflow already {w.status}")
    w.status = "cancelled"
    w.completed_at = w.completed_at
    from app.workflow.pipeline import WorkflowRepository

    await WorkflowRepository(session).log(w.id, f"Cancelled by {principal.user.name}", level="warning")
    if w.project_id:
        project = await session.get(ContentProject, w.project_id)
        if project:
            project.status = "archived"
    await session.commit()
    name, title = await _names(session, w)
    return _out(w, name, title)
