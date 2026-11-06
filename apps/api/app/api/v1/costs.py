"""Cost management: ledgers by provider/model/agent/channel, daily series, budgets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_principal, require_role
from app.core.errors import ValidationAppError
from app.db.session import get_session
from app.models import AiUsageLog, Channel, ContentProject, VideoRender, Workspace
from app.schemas import BudgetUpdate, CostOverviewOut

router = APIRouter(prefix="/costs", tags=["costs"])


@router.get("", response_model=CostOverviewOut)
async def costs(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> CostOverviewOut:
    ws = principal.workspace.id
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

    async def sum_between(start, end) -> float:  # type: ignore[no-untyped-def]
        return float(
            await session.scalar(
                select(func.coalesce(func.sum(AiUsageLog.cost_usd), 0)).where(
                    AiUsageLog.workspace_id == ws,
                    AiUsageLog.created_at >= start,
                    AiUsageLog.created_at < end,
                )
            )
            or 0
        )

    month = await sum_between(month_start, now + timedelta(days=1))
    previous = await sum_between(prev_month_start, month_start)

    async def group(column, label: str) -> list[dict]:  # type: ignore[no-untyped-def]
        rows = (
            await session.execute(
                select(column, func.sum(AiUsageLog.cost_usd), func.count(AiUsageLog.id),
                       func.coalesce(func.sum(AiUsageLog.input_tokens + AiUsageLog.output_tokens), 0))
                .where(AiUsageLog.workspace_id == ws, AiUsageLog.created_at >= month_start)
                .group_by(column)
                .order_by(func.sum(AiUsageLog.cost_usd).desc())
                .limit(20)
            )
        ).all()
        total = sum(float(r[1] or 0) for r in rows) or 1
        return [
            {
                label: r[0] or "unattributed",
                "cost_usd": round(float(r[1] or 0), 4),
                "calls": int(r[2]),
                "tokens": int(r[3]),
                "share": round(float(r[1] or 0) / total * 100, 1),
            }
            for r in rows
        ]

    daily = []
    for offset in range(13, -1, -1):
        day = (now - timedelta(days=offset)).date()
        value = float(
            await session.scalar(
                select(func.coalesce(func.sum(AiUsageLog.cost_usd), 0)).where(
                    AiUsageLog.workspace_id == ws,
                    func.date(AiUsageLog.created_at) == day,
                )
            )
            or 0
        )
        daily.append({"date": day.isoformat(), "cost_usd": round(value, 4)})

    minutes = float(
        await session.scalar(
            select(func.coalesce(func.sum(VideoRender.duration_s), 0)).where(
                VideoRender.workspace_id == ws, VideoRender.status == "ready"
            )
        )
        or 0
    ) / 60
    total_spend_all_time = float(
        await session.scalar(
            select(func.coalesce(func.sum(AiUsageLog.cost_usd), 0)).where(AiUsageLog.workspace_id == ws)
        )
        or 0
    )
    channel = await session.scalar(
        select(Channel).where(Channel.workspace_id == ws, Channel.deleted_at.is_(None)).limit(1)
    )
    channel_ceiling = None
    if channel:
        from app.models import ChannelSetting

        setting = await session.scalar(
            select(ChannelSetting).where(ChannelSetting.channel_id == channel.id)
        )
        if setting:
            channel_ceiling = float(setting.cost_ceiling_usd or 0)
    return CostOverviewOut(
        month_usd=round(month, 4),
        previous_month_usd=round(previous, 4),
        budget_usd=float(principal.workspace.monthly_budget_usd) if principal.workspace.monthly_budget_usd is not None else None,
        daily=daily,
        by_provider=await group(AiUsageLog.provider_slug, "provider"),
        by_agent=await group(AiUsageLog.agent_key, "agent"),
        by_model=await group(AiUsageLog.model, "model"),
        by_channel=await group(AiUsageLog.channel_id, "channel_id"),
        per_minute_usd=round(total_spend_all_time / minutes, 4) if minutes > 0 else None,
        budgets={"monthly": float(principal.workspace.monthly_budget_usd) if principal.workspace.monthly_budget_usd is not None else None,
                 "channel_ceiling": channel_ceiling},
    )


@router.put("/budget")
async def update_budget(
    payload: BudgetUpdate,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    workspace = await session.get(Workspace, principal.workspace.id)
    if workspace is None:
        raise ValidationAppError("Workspace not found")
    if payload.monthly_budget_usd is not None:
        workspace.monthly_budget_usd = payload.monthly_budget_usd
    if payload.channel_id and payload.channel_ceiling_usd is not None:
        channel = await session.scalar(
            select(Channel).where(
                Channel.id == payload.channel_id, Channel.workspace_id == workspace.id
            )
        )
        if channel is None:
            raise ValidationAppError("Channel not found")
        if channel.settings:
            channel.settings.cost_ceiling_usd = payload.channel_ceiling_usd
    await session.commit()
    return {"ok": True}


@router.get("/ledger")
async def ledger(
    limit: int = 100,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (
        await session.execute(
            select(AiUsageLog)
            .where(AiUsageLog.workspace_id == principal.workspace.id)
            .order_by(AiUsageLog.created_at.desc())
            .limit(min(limit, 500))
        )
    ).scalars()
    return [
        {
            "id": str(r.id),
            "at": r.created_at,
            "agent": r.agent_key,
            "provider": r.provider_slug,
            "model": r.model,
            "operation": r.operation,
            "tokens": r.input_tokens + r.output_tokens,
            "units": r.units,
            "unit_label": r.unit_label,
            "cost_usd": float(r.cost_usd or 0),
            "latency_ms": r.latency_ms,
        }
        for r in rows
    ]


__all__ = ["router", "ContentProject"]
