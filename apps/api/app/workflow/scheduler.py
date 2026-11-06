"""Scheduling: computes the next run for a channel schedule and enqueues due productions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import ApprovalRequest, Channel, ProductionWorkflow, Schedule
from app.workflow.pipeline import WorkflowRepository, runner

log = get_logger("factory.scheduler")

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def next_run(
    schedule: Schedule, reference: datetime | None = None
) -> datetime | None:
    """Next occurrence of ``start_time`` on an active weekday, in the schedule's timezone."""
    reference = reference or datetime.now(UTC)
    try:
        tz = ZoneInfo(schedule.timezone or "UTC")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    local = reference.astimezone(tz)
    days = [d for d in (schedule.days_of_week or list(DAYS)) if d in DAYS]
    if not days:
        return None
    for offset in range(0, 8):
        candidate_day = (local + timedelta(days=offset)).date()
        if DAYS[candidate_day.weekday()] not in days:
            continue
        candidate = datetime.combine(candidate_day, schedule.start_time or time(6, 0), tzinfo=tz)
        if candidate > local:
            return candidate.astimezone(UTC)
    return None


async def due_schedules(session: AsyncSession) -> list[Schedule]:
    now = datetime.now(UTC)
    result = await session.execute(
        select(Schedule)
        .join(Channel, Channel.id == Schedule.channel_id)
        .where(
            Schedule.is_enabled.is_(True),
            Channel.is_active.is_(True),
            Channel.deleted_at.is_(None),
            (Schedule.next_run_at.is_(None)) | (Schedule.next_run_at <= now),
        )
    )
    return list(result.scalars())


async def materialize_due(session: AsyncSession) -> int:
    created = 0
    repo = WorkflowRepository(session)
    for schedule in await due_schedules(session):
        channel = await session.get(Channel, schedule.channel_id)
        if channel is None:
            continue
        now = datetime.now(UTC)
        existing = await session.scalar(
            select(ProductionWorkflow.id).where(
                ProductionWorkflow.channel_id == channel.id,
                ProductionWorkflow.trigger == "schedule",
                ProductionWorkflow.created_at >= now - timedelta(hours=1),
            )
        )
        running = await session.scalar(
            select(ProductionWorkflow.id).where(
                ProductionWorkflow.channel_id == channel.id,
                ProductionWorkflow.status.notin_(("published", "failed", "cancelled")),
            )
        )
        if existing is None and running is None:
            for _ in range(max(1, min(schedule.production_count, schedule.max_concurrent))):
                wf = await repo.create(
                    workspace_id=channel.workspace_id,
                    channel_id=channel.id,
                    trigger="schedule",
                )
                await repo.log(wf.id, f"Scheduled production created from schedule “{schedule.name}”")
                created += 1
        schedule.last_run_at = now
        schedule.next_run_at = next_run(schedule, now)
    await session.commit()
    return created


async def scheduler_tick() -> int:
    from app.db.session import session_scope

    async with session_scope() as session:
        created = await materialize_due(session)
        due = list(
            (
                await session.execute(
                    select(ProductionWorkflow.id).where(
                        ProductionWorkflow.status == "pending",
                    )
                )
            ).scalars()
        )
        for wf_id in due:
            runner.submit(wf_id)
        if created:
            log.info("scheduler created %s workflows", created)
        return created


async def expire_approvals(session: AsyncSession) -> int:
    now = datetime.now(UTC)
    pending = (
        await session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.status == "pending",
                ApprovalRequest.expires_at.is_not(None),
                ApprovalRequest.expires_at < now,
            )
        )
    ).scalars()
    count = 0
    for row in pending:
        row.status = "expired"
        count += 1
    await session.commit()
    return count


def schedule_id_key(channel_id: uuid.UUID) -> str:
    return f"schedule-{channel_id}"
