"""Agent registry: status, performance, configuration and run history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_principal, require_role, write_audit
from app.core.errors import NotFoundError, ValidationAppError
from app.db.session import get_session
from app.models import Agent, AgentConfiguration, AiProvider, WorkflowTask
from app.schemas import AgentConfigIn, AgentOut, AgentRunOut

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentOut])
async def list_agents(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[AgentOut]:
    since = datetime.now(UTC) - timedelta(days=30)
    # Execution order: the registry defines the pipeline sequence, whatever the DB insertion order.
    from app.agents.registry import REGISTRY

    order = {spec.key: i for i, spec in enumerate(REGISTRY.all())}
    agents = sorted(
        (await session.execute(select(Agent))).scalars(),
        key=lambda a: order.get(a.key, 999),
    )
    stats_rows = (
        await session.execute(
            select(
                WorkflowTask.agent_key,
                func.count(WorkflowTask.id),
                func.sum(case((WorkflowTask.status == "succeeded", 1), else_=0)),
                func.avg(WorkflowTask.duration_ms),
                func.coalesce(func.sum(WorkflowTask.cost_usd), 0),
                func.max(WorkflowTask.created_at),
            )
            .where(WorkflowTask.created_at >= since)
            .group_by(WorkflowTask.agent_key)
        )
    ).all()
    stats = {row[0]: row for row in stats_rows}
    configs = list(
        (
            await session.execute(
                select(AgentConfiguration).where(AgentConfiguration.channel_id.is_(None))
            )
        ).scalars()
    )
    cfg_by_agent = {c.agent_id: c for c in configs}
    providers = {
        p.id: p
        for p in (
            await session.execute(
                select(AiProvider).where(AiProvider.workspace_id == principal.workspace.id)
            )
        ).scalars()
    }
    out: list[AgentOut] = []
    for agent in agents:
        cfg = cfg_by_agent.get(agent.id)
        provider = providers.get(cfg.provider_id) if cfg and cfg.provider_id else None
        row = stats.get(agent.key)
        executions = int(row[1]) if row else 0
        succeeded = int(row[2] or 0) if row else 0
        status = "paused"
        if agent.is_enabled and (cfg.is_enabled if cfg else True):
            external = agent.port in ("llm", "tts", "image", "youtube")
            has_provider = any(p.kind == agent.port and p.is_enabled for p in providers.values())
            status = "active" if (has_provider or not external) else "unconfigured"
        out.append(
            AgentOut(
                id=agent.id,
                key=agent.key,
                name=agent.name,
                role=agent.role,
                description=agent.description,
                category=agent.category,
                stage=agent.stage,
                port=agent.port,
                is_enabled=bool(cfg.is_enabled) if cfg else agent.is_enabled,
                provider_id=provider.id if provider else None,
                provider_name=provider.name if provider else None,
                model=cfg.model if cfg and cfg.model else None,
                temperature=float(cfg.temperature) if cfg and cfg.temperature is not None else 0.7,
                max_tokens=int(cfg.max_tokens) if cfg and cfg.max_tokens else 4096,
                system_prompt=cfg.system_prompt if cfg else None,
                default_system_prompt=agent.default_system_prompt,
                params=dict(cfg.params or {}) if cfg else {},
                executions=executions,
                success_rate=round(succeeded / executions * 100, 1) if executions else None,
                avg_duration_ms=int(row[3]) if row and row[3] else None,
                total_cost_usd=float(row[4] or 0) if row else 0.0,
                last_run_at=row[5] if row else None,
                status=status,  # type: ignore[arg-type]
            )
        )
    return out


@router.get("/{key}", response_model=AgentOut)
async def get_agent(
    key: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> AgentOut:
    items = await list_agents(principal, session)
    for item in items:
        if item.key == key:
            return item
    raise NotFoundError("Agent not found")


@router.put("/{key}/config", response_model=AgentOut)
async def configure_agent(
    key: str,
    payload: AgentConfigIn,
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> AgentOut:
    agent = await session.scalar(select(Agent).where(Agent.key == key))
    if agent is None:
        raise NotFoundError("Agent not found")
    if payload.provider_id:
        provider = await session.get(AiProvider, payload.provider_id)
        if provider is None or provider.workspace_id != principal.workspace.id:
            raise ValidationAppError("Provider does not belong to this workspace")
        if agent.port in ("llm", "tts", "image", "youtube") and provider.kind != agent.port:
            raise ValidationAppError(
                f"This agent uses a {agent.port.upper()} provider; selected provider is {provider.kind.upper()}."
            )
    cfg = await session.scalar(
        select(AgentConfiguration).where(
            AgentConfiguration.agent_id == agent.id, AgentConfiguration.channel_id.is_(None)
        )
    )
    if cfg is None:
        cfg = AgentConfiguration(agent_id=agent.id, channel_id=None)
        session.add(cfg)
    cfg.provider_id = payload.provider_id
    cfg.fallback_provider_id = payload.fallback_provider_id
    cfg.model = payload.model
    cfg.temperature = payload.temperature
    cfg.max_tokens = payload.max_tokens
    cfg.system_prompt = payload.system_prompt or None
    cfg.params = payload.params
    cfg.is_enabled = payload.is_enabled
    agent.is_enabled = payload.is_enabled
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="agent.configured", target_type="agent", target_id=key,
                      request=request, provider_id=str(payload.provider_id) if payload.provider_id else None,
                      model=payload.model, enabled=payload.is_enabled)
    await session.commit()
    return await get_agent(key, principal, session)


@router.get("/{key}/runs", response_model=list[AgentRunOut])
async def agent_runs(
    key: str,
    limit: int = 25,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[AgentRunOut]:
    rows = (
        await session.execute(
            select(WorkflowTask)
            .where(WorkflowTask.agent_key == key)
            .order_by(WorkflowTask.created_at.desc())
            .limit(min(limit, 100))
        )
    ).scalars()
    return [AgentRunOut.model_validate(r) for r in rows]


__all__ = ["router", "and_"]
