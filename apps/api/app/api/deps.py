"""Auth dependencies: current user, active workspace, RBAC, rate limiting, audit helpers."""

from __future__ import annotations

import time as _time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PermissionDeniedError, RateLimitedError, UnauthorizedError
from app.core.security import decode_access_token
from app.core.settings import get_settings
from app.db.session import get_session
from app.models import AuditLog, User, Workspace, WorkspaceMember

ROLE_ORDER = {"viewer": 1, "editor": 2, "admin": 3, "owner": 4}


@dataclass(slots=True)
class Principal:
    user: User
    workspace: Workspace
    role: str
    member: WorkspaceMember

    def require(self, minimum: str) -> None:
        if ROLE_ORDER.get(self.role, 0) < ROLE_ORDER[minimum]:
            raise PermissionDeniedError(f"Requires the {minimum} role (you are {self.role})")


async def get_principal(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Principal:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:]
    if not token:
        raise UnauthorizedError("Authentication required")
    try:
        payload = decode_access_token(token)
    except Exception as exc:  # noqa: BLE001 - any JWT failure is a 401
        raise UnauthorizedError("Session expired or invalid") from exc
    user = await session.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or disabled")
    member = await session.scalar(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id).limit(1)
    )
    if member is None:
        raise PermissionDeniedError("You are not a member of any workspace")
    workspace = await session.get(Workspace, member.workspace_id)
    if workspace is None:
        raise PermissionDeniedError("Workspace not found")
    return Principal(user=user, workspace=workspace, role=member.role, member=member)


def require_role(minimum: str):  # type: ignore[no-untyped-def]
    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        principal.require(minimum)
        return principal

    return dependency


class RateLimiter:
    """Fixed-window token bucket per (client, route group). In-process; Redis optional."""

    def __init__(self, limit_per_minute: int) -> None:
        self.limit = limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = _time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.limit:
            raise RateLimitedError("Too many requests — retry in a moment")
        window.append(now)


limiter = RateLimiter(get_settings().rate_limit_per_minute)


async def rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "anonymous"
    bucket = request.url.path.split("/")[3] if len(request.url.path.split("/")) > 3 else "root"
    limiter.check(f"{client}:{bucket}")


async def write_audit(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    request: Request | None = None,
    **metadata,
) -> None:
    session.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            ip=request.client.host if request and request.client else None,
            metadata_json=metadata,
        )
    )


class AuthLimiter(RateLimiter):
    pass


auth_limiter = RateLimiter(10)
