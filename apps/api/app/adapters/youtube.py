"""YouTube service adapter (Data API v3 resumable upload + Analytics) and a mock."""

from __future__ import annotations

import asyncio
import json

import httpx

from app.adapters.http import raise_for_status, with_retries
from app.ports.interfaces import (
    ProviderError,
    UploadRequest,
    UploadResult,
    VideoStats,
    YouTubeService,
)

_DATA = "https://www.googleapis.com/youtube/v3"
_UPLOAD = "https://www.googleapis.com/upload/youtube/v3"
_ANALYTICS = "https://youtubeanalytics.googleapis.com/v2"


class YouTubeDataService:
    name = "youtube"

    async def upload(self, access_token: str, request: UploadRequest) -> UploadResult:
        if request.scheduled_for and request.privacy != "private":
            raise ProviderError("Scheduled uploads must use private privacy until publish time")

        status: dict = {"privacyStatus": request.privacy, "selfDeclaredMadeForKids": request.made_for_kids}
        if request.scheduled_for:
            status["publishAt"] = request.scheduled_for.isoformat().replace("+00:00", "Z")
        metadata = {
            "snippet": {
                "title": request.title[:100],
                "description": request.description[:5000],
                "tags": request.tags[:30],
                "categoryId": "24",  # Entertainment (kids content category varies by policy)
            },
            "status": status,
        }

        video_bytes = request.video_bytes
        if video_bytes is None and request.video_path:
            from pathlib import Path

            video_bytes = await asyncio.to_thread(Path(request.video_path).read_bytes)
        if video_bytes is None:
            raise ProviderError("No video payload supplied")

        async def call() -> str:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": request.mime_type,
                "X-Upload-Content-Length": str(len(video_bytes or b"")),
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=20)) as client:
                init = await client.post(
                    f"{_UPLOAD}/videos",
                    params={"uploadType": "resumable", "part": "snippet,status"},
                    headers=headers,
                    content=json.dumps(metadata),
                )
            raise_for_status(init, self.name)
            session_url = init.headers.get("Location")
            if not session_url:
                raise ProviderError("Upload session URL missing from YouTube response")
            async with httpx.AsyncClient(timeout=httpx.Timeout(900, connect=20)) as client:
                put = await client.put(
                    session_url,
                    headers={"Content-Type": request.mime_type},
                    content=video_bytes,
                )
            raise_for_status(put, self.name)
            return put.json()["id"]

        video_id = await with_retries(call, attempts=3, base_delay=5)

        if request.thumbnail_bytes:
            async def set_thumb() -> None:
                async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=20)) as client:
                    resp = await client.post(
                        f"{_UPLOAD}/thumbnails/set",
                        params={"videoId": video_id},
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "image/png",
                        },
                        content=request.thumbnail_bytes,
                    )
                raise_for_status(resp, self.name)

            try:
                await with_retries(set_thumb, attempts=2)
            except ProviderError:
                # thumbnail failure must not fail a successful upload; surfaced as a warning upstream
                pass

        return UploadResult(youtube_video_id=video_id, url=f"https://www.youtube.com/watch?v={video_id}")

    async def fetch_stats(self, access_token: str, video_ids: list[str]) -> list[VideoStats]:
        if not video_ids:
            return []
        async with httpx.AsyncClient(timeout=30) as client:
            videos = await client.get(
                f"{_DATA}/videos",
                params={"part": "statistics", "id": ",".join(video_ids)},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            analytics = await client.get(
                f"{_ANALYTICS}/reports",
                params={
                    "ids": "channel==MINE",
                    "startDate": "2000-01-01",
                    "endDate": "2099-12-31",
                    "metrics": "views,estimatedMinutesWatched,averageViewDuration,"
                    "subscribersGained,likes,comments",
                    "dimensions": "video",
                    "filters": f"video=={','.join(video_ids)}",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
        raise_for_status(videos, self.name)
        stats_by_id: dict[str, dict[str, float]] = {}
        if analytics.status_code == 200:
            headers = [h["name"] for h in analytics.json().get("columnHeaders", [])]
            for row in analytics.json().get("rows", []):
                record = dict(zip(headers, row, strict=False))
                stats_by_id[str(record.get("video"))] = record
        else:
            raise ProviderError(
                f"Analytics API {analytics.status_code}: {analytics.text[:300]}"
            )
        out: list[VideoStats] = []
        for item in videos.json().get("items", []):
            vid = item["id"]
            s = stats_by_id.get(vid, {})
            st = item.get("statistics", {})
            out.append(
                VideoStats(
                    youtube_video_id=vid,
                    views=int(s.get("views", st.get("viewCount", 0)) or 0),
                    impressions=None,  # impressions/CTR require channel owner Analytics dimensions
                    ctr=None,
                    watch_time_minutes=float(s.get("estimatedMinutesWatched", 0) or 0),
                    avg_view_duration_s=_num(s.get("averageViewDuration")),
                    subscribers_gained=int(s.get("subscribersGained", 0) or 0),
                    likes=int(s.get("likes", st.get("likeCount", 0)) or 0),
                    comments=int(s.get("comments", st.get("commentCount", 0)) or 0),
                )
            )
        return out

    async def channel_info(self, access_token: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{_DATA}/channels",
                params={"part": "snippet,statistics", "mine": "true"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        raise_for_status(resp, self.name)
        items = resp.json().get("items", [])
        if not items:
            raise ProviderError("No YouTube channel found for this Google account")
        item = items[0]
        return {
            "id": item["id"],
            "title": item["snippet"]["title"],
            "subscribers": int(item.get("statistics", {}).get("subscriberCount", 0) or 0),
            "videos": int(item.get("statistics", {}).get("videoCount", 0) or 0),
        }


def _num(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class MockYouTubeService:
    """Records uploads without contacting YouTube. Used only when the provider is mock."""

    name = "mock"

    async def upload(self, access_token: str, request: UploadRequest) -> UploadResult:
        import hashlib

        digest = hashlib.sha1((request.title + (request.description or "")).encode()).hexdigest()[:10]
        return UploadResult(
            youtube_video_id=f"MOCK{digest.upper()}",
            url=f"https://youtube.example/mock/{digest}",
        )

    async def fetch_stats(self, access_token: str, video_ids: list[str]) -> list[VideoStats]:
        raise ProviderError("Mock YouTube provider has no analytics data")

    async def channel_info(self, access_token: str) -> dict:
        return {"id": "MOCKCHANNEL", "title": "Mock channel", "subscribers": 0, "videos": 0}


def build_youtube_service(slug: str) -> YouTubeService:
    if slug == "mock":
        return MockYouTubeService()
    if slug == "google":
        return YouTubeDataService()
    raise ProviderError(f"Unsupported YouTube provider '{slug}'")
