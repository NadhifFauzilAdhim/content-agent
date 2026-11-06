"""System: health, readiness, integration status, workspace/team, API keys, audit."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.media import ffmpeg_available
from app.api.deps import Principal, get_principal, require_role, write_audit
from app.core.config_view import app_config
from app.core.errors import ConflictError, NotFoundError
from app.core.security import hash_password, hash_token
from app.core.settings import get_settings
from app.db.session import get_session
from app.models import ApiKey, AuditLog, Schedule, User, Workspace, WorkspaceMember
from app.schemas import (
    ApiKeyCreate,
    ApiKeyCreatedOut,
    ApiKeyOut,
    AuditLogOut,
    InviteMemberRequest,
    MemberOut,
    SystemStatusOut,
)

router = APIRouter(tags=["system"])
public_router = APIRouter(tags=["health"])


@public_router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


@public_router.get("/readyz")
async def readyz(session: AsyncSession = Depends(get_session)) -> dict:
    from sqlalchemy import text

    checks = {"database": False, "ffmpeg": ffmpeg_available()}
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:  # noqa: BLE001
        checks["database"] = False
    return {"ready": checks["database"], "checks": checks}


@router.get("/system/status", response_model=SystemStatusOut)
async def system_status(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> SystemStatusOut:
    from app.api.v1.overview import overview
    from app.models import Channel

    data = await overview(principal, session)
    next_run = await session.scalar(
        select(func.min(Schedule.next_run_at))
        .join(Channel, Channel.id == Schedule.channel_id)
        .where(Channel.workspace_id == principal.workspace.id, Schedule.is_enabled.is_(True))
    )
    active_schedules = int(
        await session.scalar(
            select(func.count(Schedule.id))
            .join(Channel, Channel.id == Schedule.channel_id)
            .where(
                Channel.workspace_id == principal.workspace.id,
                Schedule.is_enabled.is_(True),
            )
        )
        or 0
    )
    return SystemStatusOut(
        time=datetime.now(UTC),
        services=[{"name": k, **v} for k, v in data.system.items()],
        providers=data.providers,
        scheduler={
            "enabled": get_settings().scheduler_enabled,
            "next_run_at": next_run,
            "active_schedules": active_schedules,
        },
    )


@router.get("/system/integrations")
async def integrations(principal: Principal = Depends(get_principal)) -> dict:
    return app_config()


# --------------------------------------------------------------------------- workspace / team


@router.get("/workspace")
async def workspace(principal: Principal = Depends(get_principal)) -> dict:
    w = principal.workspace
    return {
        "id": str(w.id),
        "name": w.name,
        "slug": w.slug,
        "plan": w.plan,
        "monthly_budget_usd": float(w.monthly_budget_usd) if w.monthly_budget_usd is not None else None,
        "role": principal.role,
        "created_at": w.created_at,
    }


@router.get("/workspace/members", response_model=list[MemberOut])
async def members(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[MemberOut]:
    rows = (
        await session.execute(
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == principal.workspace.id)
            .order_by(WorkspaceMember.created_at)
        )
    ).all()
    return [
        MemberOut(
            id=m.id, user_id=u.id, email=u.email, name=u.name, role=m.role,
            created_at=m.created_at, last_login_at=u.last_login_at,
        )
        for m, u in rows
    ]


@router.post("/workspace/members", response_model=MemberOut, status_code=201)
async def invite_member(
    payload: InviteMemberRequest,
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> MemberOut:
    existing = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is None:
        if not payload.password:
            raise ConflictError("A password is required to create a new user")
        user = User(
            email=payload.email.lower(),
            name=payload.name,
            password_hash=hash_password(payload.password),
        )
        session.add(user)
        await session.flush()
    else:
        user = existing
    member = WorkspaceMember(user_id=user.id, workspace_id=principal.workspace.id, role=payload.role)
    session.add(member)
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="member.invited", target_type="user", target_id=str(user.id),
                      request=request, role=payload.role)
    await session.commit()
    return MemberOut(id=member.id, user_id=user.id, email=user.email, name=user.name,
                     role=member.role, created_at=member.created_at, last_login_at=None)


@router.delete("/workspace/members/{member_id}", status_code=204)
async def remove_member(
    member_id: uuid.UUID,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> None:
    member = await session.get(WorkspaceMember, member_id)
    if member is None or member.workspace_id != principal.workspace.id:
        raise NotFoundError("Member not found")
    if member.role == "owner":
        raise ConflictError("The workspace owner cannot be removed")
    await session.delete(member)
    await session.commit()


@router.get("/workspace/audit", response_model=list[AuditLogOut])
async def audit(
    limit: int = 50,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[AuditLogOut]:
    rows = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.workspace_id == principal.workspace.id)
            .order_by(AuditLog.created_at.desc())
            .limit(min(limit, 200))
        )
    ).scalars()
    return [AuditLogOut.model_validate(r) for r in rows]


# --------------------------------------------------------------------------- api keys


@router.get("/workspace/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[ApiKeyOut]:
    rows = (
        await session.execute(
            select(ApiKey).where(
                ApiKey.workspace_id == principal.workspace.id, ApiKey.revoked_at.is_(None)
            )
        )
    ).scalars()
    return [
        ApiKeyOut(id=r.id, name=r.name, prefix=r.prefix, scopes=list(r.scopes or []),
                  created_at=r.created_at, last_used_at=r.last_used_at)
        for r in rows
    ]


@router.post("/workspace/api-keys", response_model=ApiKeyCreatedOut, status_code=201)
async def create_api_key(
    payload: ApiKeyCreate,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCreatedOut:
    token = f"fct_{secrets.token_urlsafe(32)}"
    row = ApiKey(
        workspace_id=principal.workspace.id,
        name=payload.name,
        prefix=token[:10],
        key_hash=hash_token(token),
        scopes=["workflows:read"],
        created_by=principal.user.id,
    )
    session.add(row)
    await session.commit()
    return ApiKeyCreatedOut(
        id=row.id, name=row.name, prefix=row.prefix, scopes=list(row.scopes),
        created_at=row.created_at, last_used_at=None, token=token,
    )


@router.delete("/workspace/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> None:
    row = await session.get(ApiKey, key_id)
    if row is None or row.workspace_id != principal.workspace.id:
        raise NotFoundError("API key not found")
    row.revoked_at = datetime.now(UTC)
    await session.commit()


__all__ = ["router", "public_router", "Workspace"]
