"""Central policy gate for expensive operations.

Production narration is long (hundreds of thousands of characters are *not* unusual once chunking
is enabled), so a studio convenience must not be able to silently drain a workspace budget:
every billable operation checks the monthly budget *and* a per-call estimate ceiling first and
fails with an explicit, actionable message instead of prompting the provider.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BudgetExceededError
from app.models import AiUsageLog, Workspace
from app.services.pricing import estimate

#: Above this estimate a single production request needs an explicit confirmation.
PRODUCTION_CONFIRM_USD = 3.0


async def month_spend(session: AsyncSession, workspace_id: uuid.UUID) -> float:
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spent = await session.scalar(
        select(func.coalesce(func.sum(AiUsageLog.cost_usd), 0)).where(
            AiUsageLog.workspace_id == workspace_id, AiUsageLog.created_at >= start
        )
    )
    return float(spent or 0)


async def ensure_tts_budget(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    provider: str,
    model: str,
    characters: int,
    models: list[dict] | None = None,
    confirmed: bool = False,
) -> None:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None or workspace.monthly_budget_usd is None:
        return
    budget = float(workspace.monthly_budget_usd)
    spent = await month_spend(session, workspace_id)
    if spent >= budget:
        raise BudgetExceededError(
            f"Monthly AI budget reached (${spent:.2f} of ${budget:.2f}). "
            "Raise it under Costs → Budget before generating more audio."
        )
    cost = estimate(provider=provider, model=model, characters=characters, models=models).estimated_usd
    if spent + cost > budget:
        raise BudgetExceededError(
            f"This narration would cost about ${cost:.2f} and exceed the monthly budget "
            f"(${spent:.2f} of ${budget:.2f} used). Shorten the text or raise the budget."
        )
    if cost >= PRODUCTION_CONFIRM_USD and not confirmed:
        raise BudgetExceededError(
            f"This production is estimated at ${cost:.2f} ({characters:,} characters). "
            "Start it with confirm_expensive=true to proceed."
        )
