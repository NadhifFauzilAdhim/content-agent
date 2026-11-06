"""Channel management: CRUD, settings, cast, schedules, YouTube OAuth connection."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.youtube import build_youtube_service
from app.api.deps import Principal, get_principal, require_role, write_audit
from app.core.errors import ConflictError, NotFoundError, ProviderNotConfiguredError
from app.db.session import get_session
from app.models import (
    AuditLog,
    Channel,
    ChannelCharacter,
    ChannelSetting,
    ContentProject,
    Schedule,
    YouTubeOAuthConnection,
)
from app.schemas import (
    ChannelCreate,
    ChannelOut,
    ChannelSettingsIn,
    ChannelUpdate,
    CharacterIn,
    CharacterOut,
    ScheduleIn,
    ScheduleOut,
)
from app.services import youtube_oauth
from app.workflow.scheduler import next_run

router = APIRouter(tags=["channels"])


async def _settings_out(session: AsyncSession, channel: Channel) -> ChannelSettingsIn | None:
    s = await session.scalar(select(ChannelSetting).where(ChannelSetting.channel_id == channel.id))
    if s is None:
        return None
    return ChannelSettingsIn(
        visual_style=s.visual_style,
        palette=dict(s.palette or {}),
        content_guidelines=s.content_guidelines,
        banned_topics=list(s.banned_topics or []),
        made_for_kids=s.made_for_kids,
        target_duration_seconds=s.target_duration_seconds,
        cost_ceiling_usd=float(s.cost_ceiling_usd or 0),
        approval_mode=s.approval_mode,  # type: ignore[arg-type]
        min_quality_score=float(s.min_quality_score or 0),
        voice_provider=s.voice_provider,
        voice_id=s.voice_id,
        thumbnail_style=s.thumbnail_style,
    )


async def _channel_out(session: AsyncSession, channel: Channel) -> ChannelOut:
    productions = await session.scalar(
        select(func.count(ContentProject.id)).where(
            ContentProject.channel_id == channel.id, ContentProject.deleted_at.is_(None)
        )
    )
    published = await session.scalar(
        select(func.count(ContentProject.id)).where(
            ContentProject.channel_id == channel.id, ContentProject.status == "published"
        )
    )
    schedule = await session.scalar(
        select(Schedule).where(Schedule.channel_id == channel.id, Schedule.is_enabled.is_(True))
    )
    return ChannelOut(
        id=channel.id,
        name=channel.name,
        handle=channel.handle,
        description=channel.description,
        niche=channel.niche,
        audience=channel.audience,
        language=channel.language,
        video_format=channel.video_format,
        accent_color=channel.accent_color,
        is_active=channel.is_active,
        youtube_channel_id=channel.youtube_channel_id,
        youtube_channel_title=channel.youtube_channel_title,
        youtube_connected_at=channel.youtube_connected_at,
        created_at=channel.created_at,
        settings=await _settings_out(session, channel),
        characters=[CharacterOut.model_validate(c) for c in channel.characters],
        production_count=int(productions or 0),
        published_count=int(published or 0),
        next_run_at=schedule.next_run_at if schedule else None,
    )


async def _get_channel(session: AsyncSession, principal: Principal, channel_id: uuid.UUID) -> Channel:
    channel = await session.scalar(
        select(Channel).where(
            Channel.id == channel_id,
            Channel.workspace_id == principal.workspace.id,
            Channel.deleted_at.is_(None),
        ).options(selectinload(Channel.settings), selectinload(Channel.characters))
    )
    if channel is None:
        raise NotFoundError("Channel not found")
    return channel


async def _apply_settings(session: AsyncSession, channel: Channel, data: ChannelSettingsIn) -> None:
    s = await session.scalar(select(ChannelSetting).where(ChannelSetting.channel_id == channel.id))
    if s is None:
        s = ChannelSetting(channel_id=channel.id)
        session.add(s)
    s.visual_style = data.visual_style
    s.palette = data.palette
    s.content_guidelines = data.content_guidelines
    s.banned_topics = data.banned_topics
    s.made_for_kids = data.made_for_kids
    s.target_duration_seconds = data.target_duration_seconds
    s.cost_ceiling_usd = data.cost_ceiling_usd
    s.approval_mode = data.approval_mode
    s.min_quality_score = data.min_quality_score
    s.voice_provider = data.voice_provider
    s.voice_id = data.voice_id
    s.thumbnail_style = data.thumbnail_style
    await session.flush()


@router.get("/channels", response_model=list[ChannelOut])
async def list_channels(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[ChannelOut]:
    rows = (
        await session.execute(
            select(Channel)
            .where(Channel.workspace_id == principal.workspace.id, Channel.deleted_at.is_(None))
            .options(selectinload(Channel.settings), selectinload(Channel.characters))
            .order_by(Channel.created_at)
        )
    ).scalars()
    return [await _channel_out(session, c) for c in rows]


@router.post("/channels", response_model=ChannelOut, status_code=201)
async def create_channel(
    payload: ChannelCreate,
    request: Request,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> ChannelOut:
    duplicate = await session.scalar(
        select(Channel.id).where(
            Channel.workspace_id == principal.workspace.id,
            Channel.handle == payload.handle,
            Channel.deleted_at.is_(None),
        )
    )
    if duplicate:
        raise ConflictError(f"A channel with handle {payload.handle} already exists")
    channel = Channel(
        workspace_id=principal.workspace.id,
        name=payload.name,
        handle=payload.handle,
        description=payload.description,
        niche=payload.niche,
        audience=payload.audience,
        language=payload.language,
        video_format=payload.video_format,
        accent_color=payload.accent_color,
    )
    session.add(channel)
    await session.flush()
    await _apply_settings(session, channel, payload.settings or ChannelSettingsIn())
    schedule = Schedule(channel_id=channel.id)
    schedule.next_run_at = next_run(schedule)
    session.add(schedule)
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="channel.created", target_type="channel", target_id=str(channel.id),
                      request=request)
    await session.commit()
    await session.refresh(channel, attribute_names=["settings", "characters", "schedules"])
    return await _channel_out(session, channel)


@router.get("/channels/{channel_id}", response_model=ChannelOut)
async def get_channel(
    channel_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> ChannelOut:
    return await _channel_out(session, await _get_channel(session, principal, channel_id))


@router.patch("/channels/{channel_id}", response_model=ChannelOut)
async def update_channel(
    channel_id: uuid.UUID,
    payload: ChannelUpdate,
    request: Request,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> ChannelOut:
    channel = await _get_channel(session, principal, channel_id)
    data = payload.model_dump(exclude_unset=True)
    settings = data.pop("settings", None)
    for field, value in data.items():
        if value is not None:
            setattr(channel, field, value)
    if settings:
        await _apply_settings(session, channel, ChannelSettingsIn.model_validate(settings))
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="channel.updated", target_type="channel", target_id=str(channel.id),
                      request=request, fields=list(data) + (["settings"] if settings else []))
    await session.commit()
    await session.refresh(channel, attribute_names=["settings", "characters", "schedules"])
    return await _channel_out(session, channel)


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> None:
    channel = await _get_channel(session, principal, channel_id)
    channel.deleted_at = datetime.now(UTC)
    channel.is_active = False
    await write_audit(session, workspace_id=principal.workspace.id, actor_id=principal.user.id,
                      action="channel.deleted", target_type="channel", target_id=str(channel.id),
                      request=request)
    await session.commit()


# --------------------------------------------------------------------------- characters


@router.put("/channels/{channel_id}/characters", response_model=list[CharacterOut])
async def replace_characters(
    channel_id: uuid.UUID,
    characters: list[CharacterIn],
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> list[CharacterOut]:
    channel = await _get_channel(session, principal, channel_id)
    for existing in list(channel.characters):
        await session.delete(existing)
    await session.flush()
    out = []
    for data in characters:
        row = ChannelCharacter(channel_id=channel.id, **data.model_dump())
        session.add(row)
        out.append(row)
    await session.commit()
    return [CharacterOut.model_validate(r) for r in out]


# --------------------------------------------------------------------------- schedules


@router.get("/channels/{channel_id}/schedules", response_model=list[ScheduleOut])
async def list_schedules(
    channel_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[ScheduleOut]:
    await _get_channel(session, principal, channel_id)
    rows = (
        await session.execute(select(Schedule).where(Schedule.channel_id == channel_id))
    ).scalars()
    return [ScheduleOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/channels/{channel_id}/schedules", response_model=ScheduleOut, status_code=201)
async def create_schedule(
    channel_id: uuid.UUID,
    payload: ScheduleIn,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> ScheduleOut:
    await _get_channel(session, principal, channel_id)
    _validate_tz(payload.timezone)
    schedule = Schedule(channel_id=channel_id, **payload.model_dump())
    schedule.next_run_at = next_run(schedule)
    session.add(schedule)
    await session.commit()
    return ScheduleOut.model_validate(schedule, from_attributes=True)


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(
    schedule_id: uuid.UUID,
    payload: ScheduleIn,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> ScheduleOut:
    schedule = await session.scalar(
        select(Schedule)
        .join(Channel, Channel.id == Schedule.channel_id)
        .where(Schedule.id == schedule_id, Channel.workspace_id == principal.workspace.id)
    )
    if schedule is None:
        raise NotFoundError("Schedule not found")
    _validate_tz(payload.timezone)
    for field, value in payload.model_dump().items():
        setattr(schedule, field, value)
    schedule.next_run_at = next_run(schedule) if schedule.is_enabled else None
    await session.commit()
    return ScheduleOut.model_validate(schedule, from_attributes=True)


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: uuid.UUID,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> None:
    schedule = await session.scalar(
        select(Schedule)
        .join(Channel, Channel.id == Schedule.channel_id)
        .where(Schedule.id == schedule_id, Channel.workspace_id == principal.workspace.id)
    )
    if schedule is None:
        raise NotFoundError("Schedule not found")
    await session.delete(schedule)
    await session.commit()


def _validate_tz(name: str) -> None:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ConflictError(f"Unknown timezone '{name}'") from exc


# --------------------------------------------------------------------------- youtube oauth


@router.get("/youtube/status")
async def youtube_status(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from app.core.config_view import app_config

    cfg = app_config()
    connections = (
        await session.execute(
            select(YouTubeOAuthConnection)
            .join(Channel, Channel.id == YouTubeOAuthConnection.channel_id)
            .where(Channel.workspace_id == principal.workspace.id)
        )
    ).scalars()
    return {
        "oauth_configured": cfg["google_oauth_configured"],
        "connections": [
            {
                "channel_id": str(c.channel_id),
                "youtube_channel_id": c.youtube_channel_id,
                "channel_title": c.channel_title,
                "scopes": (c.scopes or "").split(),
                "last_error": c.last_error,
            }
            for c in connections
        ],
    }


@router.post("/channels/{channel_id}/youtube/connect")
async def youtube_connect(
    channel_id: uuid.UUID,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    channel = await _get_channel(session, principal, channel_id)
    if not youtube_oauth.oauth_configured():
        raise ProviderNotConfiguredError(
            "Google OAuth is not configured on the server (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)."
        )
    state = secrets.token_urlsafe(24)
    session.add(
        AuditLog(
            workspace_id=channel.workspace_id,
            actor_id=principal.user.id,
            action="youtube.oauth_started",
            target_type="channel",
            target_id=str(channel.id),
            metadata_json={"state": state},
        )
    )
    await session.commit()
    # state embeds the channel id so the callback can resolve it; the audit row proves it was issued
    return {"authorization_url": youtube_oauth.consent_url(f"{channel.id}:{state}")}


@router.post("/channels/{channel_id}/youtube/disconnect", status_code=204)
async def youtube_disconnect(
    channel_id: uuid.UUID,
    principal: Principal = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> None:
    channel = await _get_channel(session, principal, channel_id)
    conn = await session.scalar(
        select(YouTubeOAuthConnection).where(YouTubeOAuthConnection.channel_id == channel_id)
    )
    if conn:
        await session.delete(conn)
    channel.youtube_channel_id = None
    channel.youtube_channel_title = None
    channel.youtube_connected_at = None
    await session.commit()


@router.get("/youtube/callback")
async def youtube_callback(code: str, state: str, session: AsyncSession = Depends(get_session)):
    """Google redirects here; we store encrypted tokens then bounce back to the app."""
    from fastapi.responses import RedirectResponse

    from app.core.settings import get_settings

    channel_id_str = state.split(":", 1)[0]
    try:
        channel_id = uuid.UUID(channel_id_str)
    except ValueError:
        raise ConflictError("Invalid OAuth state") from None
    started = await session.scalar(
        select(AuditLog)
        .where(AuditLog.target_id == str(channel_id), AuditLog.action == "youtube.oauth_started")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    if started is None or state.split(":", 1)[-1] != (started.metadata_json or {}).get("state"):
        raise ConflictError("OAuth state mismatch — restart the connection flow")
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise NotFoundError("Channel not found")
    tokens = await youtube_oauth.exchange_code(code)
    service = build_youtube_service("google")
    info = await service.channel_info(tokens["access_token"])
    await youtube_oauth.store_connection(
        session, channel, tokens, info, tokens.get("scope", " ".join(youtube_oauth.SCOPES)).split()
    )
    session.add(
        AuditLog(
            workspace_id=channel.workspace_id,
            action="youtube.connected",
            target_type="channel",
            target_id=str(channel.id),
            metadata_json={"youtube_channel_id": info["id"]},
        )
    )
    await session.commit()
    return RedirectResponse(f"{get_settings().web_origin}/channels/{channel.id}?youtube=connected")
