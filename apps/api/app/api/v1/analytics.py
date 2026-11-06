"""YouTube analytics: snapshots collection and dashboard aggregation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.youtube import build_youtube_service
from app.api.deps import Principal, get_principal, require_role
from app.core.config_view import app_config
from app.core.errors import ProviderNotConfiguredError
from app.db.session import get_session
from app.models import AnalyticsSnapshot, Channel, YouTubeVideo
from app.schemas import AnalyticsOut
from app.services.youtube_oauth import refresh_access_token

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsOut)
async def analytics(
    days: int = 28,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsOut:
    ws = principal.workspace.id
    videos = list(
        (
            await session.execute(
                select(YouTubeVideo).where(YouTubeVideo.workspace_id == ws).order_by(
                    YouTubeVideo.published_at.desc().nullslast()
                )
            )
        ).scalars()
    )
    captured = int(
        await session.scalar(
            select(func.count(AnalyticsSnapshot.id)).where(AnalyticsSnapshot.workspace_id == ws)
        )
        or 0
    )
    cfg = app_config()
    configured = cfg["google_oauth_configured"] and any(v for v in videos if not v.youtube_video_id.startswith("MOCK"))
    detail = (
        "Analytics collected from YouTube Analytics API."
        if captured and configured
        else (
            "No analytics snapshots yet. Connect a channel and run Sync to collect data."
            if configured
            else "YouTube OAuth is not configured on the server. Set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET "
            "to collect analytics."
        )
    )
    latest: dict[str, AnalyticsSnapshot] = {}
    for snap in (
        await session.execute(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.workspace_id == ws)
            .order_by(AnalyticsSnapshot.captured_at)
        )
    ).scalars():
        latest[snap.youtube_video_id] = snap
    trend_map: dict[str, dict[str, float]] = {}
    for snap in (await session.execute(
        select(AnalyticsSnapshot)
        .where(
            AnalyticsSnapshot.workspace_id == ws,
            AnalyticsSnapshot.captured_at >= datetime.now(UTC) - timedelta(days=days),
        )
    )).scalars():
        day = snap.captured_at.date().isoformat()
        row = trend_map.setdefault(day, {"views": 0, "watch_time_minutes": 0, "subscribers": 0})
        row["views"] += snap.views
        row["watch_time_minutes"] += snap.watch_time_minutes
        row["subscribers"] += snap.subscribers_gained
    totals = {
        "views": sum(s.views for s in latest.values()),
        "watch_time_minutes": round(sum(s.watch_time_minutes for s in latest.values()), 1),
        "avg_view_duration_s": round(
            sum((s.avg_view_duration_s or 0) * s.views for s in latest.values())
            / max(1, sum(s.views for s in latest.values())),
            1,
        ),
        "subscribers_gained": sum(s.subscribers_gained for s in latest.values()),
        "ctr": next((s.ctr for s in latest.values() if s.ctr is not None), None) or 0,
    }
    return AnalyticsOut(
        configured=configured and captured > 0,
        detail=detail,
        totals=totals,
        trend=[{"date": d, **v} for d, v in sorted(trend_map.items())],
        videos=[
            {
                "id": v.id.hex,
                "youtube_video_id": v.youtube_video_id,
                "title": v.title,
                "url": v.url,
                "published_at": v.published_at.isoformat() if v.published_at else None,
                "views": latest.get(v.youtube_video_id).views if v.youtube_video_id in latest else None,
                "watch_time_minutes": latest.get(v.youtube_video_id).watch_time_minutes
                if v.youtube_video_id in latest else None,
                "avg_view_duration_s": latest.get(v.youtube_video_id).avg_view_duration_s
                if v.youtube_video_id in latest else None,
                "subscribers_gained": latest.get(v.youtube_video_id).subscribers_gained
                if v.youtube_video_id in latest else None,
                "is_mock": v.youtube_video_id.startswith("MOCK"),
            }
            for v in videos
        ],
    )


@router.post("/sync")
async def sync(
    channel_id: str | None = None,
    principal: Principal = Depends(require_role("editor")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    cfg = app_config()
    if not cfg["google_oauth_configured"]:
        raise ProviderNotConfiguredError(
            "YouTube OAuth is not configured (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)."
        )
    query = select(Channel).where(
        Channel.workspace_id == principal.workspace.id,
        Channel.deleted_at.is_(None),
        Channel.youtube_channel_id.is_not(None),
    )
    if channel_id:
        query = query.where(Channel.id == channel_id)
    channels = list((await session.execute(query)).scalars())
    if not channels:
        raise ProviderNotConfiguredError("No channel has a connected YouTube account")
    service = build_youtube_service("google")
    collected = 0
    for channel in channels:
        token = await refresh_access_token(session, channel)
        ids = list(
            (
                await session.execute(
                    select(YouTubeVideo.youtube_video_id).where(
                        YouTubeVideo.channel_id == channel.id
                    )
                )
            ).scalars()
        )
        ids = [i for i in ids if not i.startswith("MOCK")]
        if not ids:
            continue
        stats = await service.fetch_stats(token, ids)
        for s in stats:
            session.add(
                AnalyticsSnapshot(
                    workspace_id=principal.workspace.id,
                    youtube_video_id=s.youtube_video_id,
                    captured_at=datetime.now(UTC),
                    views=s.views,
                    impressions=s.impressions,
                    ctr=s.ctr,
                    watch_time_minutes=s.watch_time_minutes,
                    avg_view_duration_s=s.avg_view_duration_s,
                    subscribers_gained=s.subscribers_gained,
                    likes=s.likes,
                    comments=s.comments,
                )
            )
            collected += 1
    await session.commit()
    return {"snapshots": collected, "channels": len(channels)}
