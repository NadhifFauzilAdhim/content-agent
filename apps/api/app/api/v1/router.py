"""v1 API composition."""

from fastapi import APIRouter

from app.api.v1 import (
    agents,
    analytics,
    approvals,
    auth,
    channels,
    content,
    costs,
    files,
    overview,
    providers,
    system,
    tts,
    video,
    workflows,
)

api_router = APIRouter()
api_router.include_router(system.public_router)
api_router.include_router(auth.router)
api_router.include_router(overview.router)
api_router.include_router(channels.router)
api_router.include_router(content.router)
api_router.include_router(workflows.router)
api_router.include_router(agents.router)
api_router.include_router(providers.router)
api_router.include_router(tts.router)
api_router.include_router(video.router)
api_router.include_router(approvals.router)
api_router.include_router(costs.router)
api_router.include_router(analytics.router)
api_router.include_router(files.router)
api_router.include_router(system.router)
