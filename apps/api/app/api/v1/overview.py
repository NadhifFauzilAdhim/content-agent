"""Overview dashboard: every metric is derived from stored rows, never synthesized."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.media import ffmpeg_available
from app.api.deps import Principal, get_principal
from app.api.v1.content import _project_out
from app.api.v1.workflows import _out as workflow_out
from app.core.config_view import app_config
from app.db.session import get_session
from app.models import (
    Agent,
    AiProvider,
    AiUsageLog,
    ApprovalRequest,
    Channel,
    ContentProject,
    ProductionWorkflow,
    WorkflowTask,
    Workspace,
)
from app.schemas import MetricValue, OverviewOut

router = APIRouter(prefix="/overview", tags=["overview"])

WINDOW_DAYS = 30


def _ratio(a: float, b: float) -> float:
    return round(a / b * 100, 1) if b else 0.0


@router.get("", response_model=OverviewOut)
async def overview(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> OverviewOut:
    ws = principal.workspace.id
    now = datetime.now(UTC)
    since = now - timedelta(days=WINDOW_DAYS)
    prev_since = since - timedelta(days=WINDOW_DAYS)

    async def count(model, *conds) -> int:  # type: ignore[no-untyped-def]
        return int(await session.scalar(select(func.count(model.id)).where(*conds)) or 0)

    async def count_between(model, column, *conds) -> tuple[int, int]:  # type: ignore[no-untyped-def]
        current = int(
            await session.scalar(
                select(func.count(model.id)).where(*conds, column >= since)
            )
            or 0
        )
        previous = int(
            await session.scalar(
                select(func.count(model.id)).where(*conds, column >= prev_since, column < since)
            )
            or 0
        )
        return current, previous

    channels = await count(Channel, Channel.workspace_id == ws, Channel.deleted_at.is_(None))
    gen_cur, gen_prev = await count_between(
        ContentProject, ContentProject.created_at,
        ContentProject.workspace_id == ws, ContentProject.deleted_at.is_(None),
    )
    pub_cur, pub_prev = await count_between(
        ContentProject, ContentProject.created_at,
        ContentProject.workspace_id == ws, ContentProject.status == "published",
    )
    pending = await count(ApprovalRequest, ApprovalRequest.workspace_id == ws,
                          ApprovalRequest.status == "pending")
    active = int(
        await session.scalar(
            select(func.count(ProductionWorkflow.id)).where(
                ProductionWorkflow.workspace_id == ws,
                ProductionWorkflow.status.notin_(("published", "failed", "cancelled")),
            )
        )
        or 0
    )
    failed_cur, failed_prev = await count_between(
        ProductionWorkflow, ProductionWorkflow.created_at,
        ProductionWorkflow.workspace_id == ws, ProductionWorkflow.status == "failed",
    )
    produced_cur = int(
        await session.scalar(
            select(func.count(ProductionWorkflow.id)).where(
                ProductionWorkflow.workspace_id == ws,
                ProductionWorkflow.created_at >= since,
                ProductionWorkflow.status.in_(("published", "awaiting_approval", "failed")),
            )
        )
        or 0
    )
    success_rate = _ratio(produced_cur - failed_cur, produced_cur) if produced_cur else 0.0
    spend_month = float(
        await session.scalar(
            select(func.coalesce(func.sum(AiUsageLog.cost_usd), 0)).where(
                AiUsageLog.workspace_id == ws,
                AiUsageLog.created_at >= now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            )
        )
        or 0
    )

    totals = {
        "channels": MetricValue(value=channels, label="channels", caption="active workspace"),
        "generated": MetricValue(value=gen_cur, previous=gen_prev, label="videos generated",
                                 caption=f"last {WINDOW_DAYS}d"),
        "published": MetricValue(value=pub_cur, previous=pub_prev, label="videos published",
                                 caption=f"last {WINDOW_DAYS}d"),
        "pending_approvals": MetricValue(value=pending, label="pending approvals",
                                         caption="awaiting review"),
        "active_workflows": MetricValue(value=active, label="active workflows", caption="in production"),
        "failed": MetricValue(value=failed_cur, previous=failed_prev, label="failed workflows",
                              caption=f"last {WINDOW_DAYS}d"),
        "spend": MetricValue(value=round(spend_month, 2), label="AI spend", caption="month to date · usd"),
        "success_rate": MetricValue(value=success_rate, label="success rate",
                                    caption=f"{produced_cur} completed runs"),
    }

    # production activity: last 14 days, created vs published
    activity = []
    for offset in range(13, -1, -1):
        day = (now - timedelta(days=offset)).date()
        created = int(
            await session.scalar(
                select(func.count(ContentProject.id)).where(
                    ContentProject.workspace_id == ws,
                    func.date(ContentProject.created_at) == day,
                )
            )
            or 0
        )
        published = int(
            await session.scalar(
                select(func.count(ContentProject.id)).where(
                    ContentProject.workspace_id == ws,
                    ContentProject.status == "published",
                    func.date(ContentProject.created_at) == day,
                )
            )
            or 0
        )
        activity.append({"date": day.isoformat(), "created": created, "published": published})

    # agent activity (traffic map) over window
    agent_rows = (
        await session.execute(
            select(
                WorkflowTask.agent_key,
                func.count(WorkflowTask.id),
                func.sum(case((WorkflowTask.status == "succeeded", 1), else_=0)),
                func.avg(WorkflowTask.duration_ms),
                func.coalesce(func.sum(WorkflowTask.cost_usd), 0),
            )
            .join(ProductionWorkflow, ProductionWorkflow.id == WorkflowTask.workflow_id)
            .where(ProductionWorkflow.workspace_id == ws, WorkflowTask.created_at >= since)
            .group_by(WorkflowTask.agent_key)
        )
    ).all()
    agent_meta = {a.key: a for a in (await session.execute(select(Agent))).scalars()}
    agent_activity = [
        {
            "key": key,
            "name": agent_meta[key].name if key in agent_meta else key,
            "stage": agent_meta[key].stage if key in agent_meta else "",
            "executions": int(runs),
            "success_rate": _ratio(int(ok or 0), int(runs)),
            "avg_duration_ms": int(avg or 0),
            "cost_usd": float(cost or 0),
        }
        for key, runs, ok, avg, cost in agent_rows
    ]

    # channel routing for the map
    channel_flows = []
    for ch in (await session.execute(
        select(Channel).where(Channel.workspace_id == ws, Channel.deleted_at.is_(None))
    )).scalars():
        runs = int(
            await session.scalar(
                select(func.count(ProductionWorkflow.id)).where(
                    ProductionWorkflow.channel_id == ch.id, ProductionWorkflow.created_at >= since
                )
            )
            or 0
        )
        channel_flows.append({"id": str(ch.id), "name": ch.name, "handle": ch.handle,
                              "runs": runs, "is_active": ch.is_active})

    recent_projects = []
    for p in (
        await session.execute(
            select(ContentProject)
            .where(ContentProject.workspace_id == ws, ContentProject.deleted_at.is_(None))
            .order_by(ContentProject.created_at.desc())
            .limit(6)
        )
    ).scalars():
        recent_projects.append(await _project_out(session, p))

    recent_workflows = []
    for w in (
        await session.execute(
            select(ProductionWorkflow)
            .where(ProductionWorkflow.workspace_id == ws)
            .order_by(ProductionWorkflow.created_at.desc())
            .limit(6)
        )
    ).scalars():
        channel = await session.get(Channel, w.channel_id)
        project = await session.get(ContentProject, w.project_id) if w.project_id else None
        recent_workflows.append(
            workflow_out(w, channel.name if channel else "—", project.title if project else None)
        )

    providers = [
        {
            "id": str(p.id), "name": p.name, "kind": p.kind, "health": p.health,
            "detail": p.health_detail, "is_mock": p.is_mock, "is_enabled": p.is_enabled,
        }
        for p in (
            await session.execute(
                select(AiProvider)
                .where(AiProvider.workspace_id == ws)
                .order_by(AiProvider.kind)
            )
        ).scalars()
    ]
    cfg = app_config()
    system = {
        "api": {"status": "ok", "detail": "API responding"},
        "database": {"status": "ok", "detail": session.bind.dialect.name if session.bind else ""},
        "ffmpeg": {"status": "ok" if ffmpeg_available() else "unconfigured",
                   "detail": "Renderer available" if ffmpeg_available() else "Install FFmpeg to render"},
        "youtube": {"status": "ok" if cfg["google_oauth_configured"] else "unconfigured",
                    "detail": "OAuth client configured" if cfg["google_oauth_configured"]
                    else "Set Google OAuth credentials"},
        "workflow": {"status": "ok", "detail": f"{cfg['workflow_backend']} backend"},
        "scheduler": {"status": "ok" if cfg["scheduler_enabled"] else "paused",
                      "detail": "enabled" if cfg["scheduler_enabled"] else "disabled"},
    }
    return OverviewOut(
        totals=totals,
        production_activity=activity,
        agent_activity=agent_activity,
        channels=channel_flows,
        recent_projects=recent_projects,
        recent_workflows=recent_workflows,
        system=system,
        providers=providers,
    )


__all__ = ["router", "Workspace"]
