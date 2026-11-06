"""Human-in-the-loop approvals. Publishing is blocked until a decision is recorded."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_principal, require_role, write_audit
from app.core.errors import ConflictError, NotFoundError, WorkflowStateError
from app.db.session import get_session
from app.models import ApprovalRequest, Channel, ContentProject, ProductionWorkflow
from app.schemas import ApprovalDecision, ApprovalOut
from app.workflow.pipeline import ProductionPipeline, runner

router = APIRouter(prefix="/approvals", tags=["approvals"])


async def _out(session: AsyncSession, a: ApprovalRequest) -> ApprovalOut:
    project = await session.get(ContentProject, a.project_id)
    channel = await session.get(Channel, project.channel_id) if project else None
    return ApprovalOut(
        id=a.id,
        project_id=a.project_id,
        project_title=project.title if project else "—",
        channel_name=channel.name if channel else "—",
        workflow_id=a.workflow_id,
        kind=a.kind,
        status=a.status,
        summary=dict(a.summary or {}),
        created_at=a.created_at,
        decided_at=a.decided_at,
        decision_note=a.decision_note,
    )


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    status: str | None = "pending",
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[ApprovalOut]:
    query = (
        select(ApprovalRequest)
        .where(ApprovalRequest.workspace_id == principal.workspace.id)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(100)
    )
    if status:
        query = query.where(ApprovalRequest.status == status)
    rows = list((await session.execute(query)).scalars())
    return [await _out(session, a) for a in rows]


@router.post("/{approval_id}/decision", response_model=ApprovalOut)
async def decide(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    request: Request,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> ApprovalOut:
    approval = await session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.workspace_id == principal.workspace.id,
        )
    )
    if approval is None:
        raise NotFoundError("Approval not found")
    if approval.status != "pending":
        raise ConflictError(f"Approval already {approval.status}")
    approval.status = "approved" if payload.decision == "approve" else "rejected"
    approval.reviewer_id = principal.user.id
    approval.decision_note = payload.note
    approval.decided_at = datetime.now(UTC)
    project = await session.get(ContentProject, approval.project_id)
    workflow = (
        await session.get(ProductionWorkflow, approval.workflow_id) if approval.workflow_id else None
    )
    if project:
        project.status = "approved" if approval.status == "approved" else "rejected"
    channel = await session.get(Channel, project.channel_id) if project else None
    can_publish = bool(channel and channel.youtube_channel_id)
    if approval.status == "approved" and workflow is not None and not can_publish:
        # Approval recorded, but the channel is not connected: the workflow stays awaiting approval
        # with a clear error instead of pretending to publish.
        workflow.error_message = (
            "Approved, but this channel has no YouTube connection. Connect it under Channels → "
            "YouTube, then use Retry on the workflow."
        )
        approval.status = "approved"
        await session.commit()
        return await _out(session, approval)
    if approval.status == "approved" and workflow is not None:
        # Publishing is an explicit consequence of approval, not a silent immediate action:
        # it is queued as a durable job on the workflow and executed by the runner.
        workflow.status = "publishing"
        workflow.stage = "publishing"
        workflow.current_agent_key = "publishing"
        await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                          action="approval.approved", target_type="approval",
                          target_id=str(approval.id), request=request)
        await session.commit()
        runner.submit_publish(workflow.id)
        from app.workflow.temporal_adapter import signal_approval

        await signal_approval(str(workflow.id), payload.note)
    else:
        if approval.status == "rejected" and workflow is not None:
            workflow.status = "cancelled"
            workflow.completed_at = datetime.now(UTC)
            from app.workflow.temporal_adapter import signal_cancel

            await signal_cancel(str(workflow.id))
        await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                          action="approval.rejected", target_type="approval",
                          target_id=str(approval.id), request=request, note=payload.note)
        await session.commit()
    return await _out(session, approval)


@router.post("/{approval_id}/expire", response_model=ApprovalOut)
async def expire(
    approval_id: uuid.UUID,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> ApprovalOut:
    approval = await session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.workspace_id == principal.workspace.id,
        )
    )
    if approval is None:
        raise NotFoundError("Approval not found")
    if approval.status != "pending":
        raise WorkflowStateError("Only pending approvals can be expired")
    approval.status = "expired"
    approval.decided_at = datetime.now(UTC)
    await session.commit()
    return await _out(session, approval)


__all__ = ["router", "ProductionPipeline"]
