"""Authentication endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, auth_limiter, get_principal, write_audit
from app.core.config_view import app_config
from app.core.errors import UnauthorizedError, ValidationAppError
from app.core.security import create_access_token, hash_password, verify_password
from app.core.settings import get_settings
from app.db.session import get_session
from app.models import User, Workspace, WorkspaceMember
from app.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    SessionOut,
    UserOut,
    WorkspaceBrief,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _workspaces(member_role: str, workspace: Workspace) -> list[WorkspaceBrief]:
    return [WorkspaceBrief(id=workspace.id, name=workspace.name, slug=workspace.slug, role=member_role)]


@router.post("/login", response_model=SessionOut)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> SessionOut:
    auth_limiter.check(f"login:{request.client.host if request.client else 'unknown'}")
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        await write_audit(session, workspace_id=None, actor_id=None, action="auth.login_failed",
                          request=request, email=payload.email)
        await session.commit()
        raise UnauthorizedError("Incorrect email or password")
    if not user.is_active:
        raise UnauthorizedError("Account disabled")
    member = await session.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id).limit(1))
    if member is None:
        raise UnauthorizedError("No workspace membership")
    workspace = await session.get(Workspace, member.workspace_id)
    if workspace is None:
        raise UnauthorizedError("Workspace missing")
    user.last_login_at = datetime.now(UTC)
    token = create_access_token(str(user.id), {"wid": str(workspace.id), "role": member.role})
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.cookie_secure or settings.is_production,
        samesite="lax",
        max_age=settings.access_token_ttl_minutes * 60,
        path="/",
    )
    await write_audit(session, workspace_id=workspace.id, actor_id=user.id, action="auth.login",
                      request=request)
    await session.commit()
    return SessionOut(
        user=UserOut.model_validate(user),
        workspace=_workspaces(member.role, workspace)[0],
        workspaces=_workspaces(member.role, workspace),
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.access_token_ttl_minutes),
    )


@router.post("/logout")
async def logout(
    response: Response,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="auth.logout")
    await session.commit()
    return {"ok": True}


@router.get("/session", response_model=SessionOut)
async def session_info(principal: Principal = Depends(get_principal)) -> SessionOut:
    return SessionOut(
        user=UserOut.model_validate(principal.user),
        workspace=WorkspaceBrief(
            id=principal.workspace.id, name=principal.workspace.name,
            slug=principal.workspace.slug, role=principal.role,
        ),
        workspaces=[WorkspaceBrief(
            id=principal.workspace.id, name=principal.workspace.name,
            slug=principal.workspace.slug, role=principal.role,
        )],
        expires_at=datetime.now(UTC) + timedelta(minutes=get_settings().access_token_ttl_minutes),
    )


@router.post("/password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not verify_password(payload.current_password, principal.user.password_hash):
        raise ValidationAppError("Current password is incorrect")
    principal.user.password_hash = hash_password(payload.new_password)
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="auth.password_changed", request=request)
    await session.commit()
    return {"ok": True}


@router.get("/config")
async def public_config() -> dict:
    """Non-secret configuration the web app needs to render setup states."""
    return app_config()


@router.get("/me", response_model=UserOut)
async def me(principal: Principal = Depends(get_principal)) -> UserOut:
    return UserOut.model_validate(principal.user)


__all__ = ["router", "uuid"]
