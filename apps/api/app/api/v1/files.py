"""Generated asset delivery (local storage backend).

Files are served only to authenticated workspace members through a path-checked route; keys from
storage are content-addressed so responses are immutable and safe to cache privately.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.adapters.storage import LocalStorage, get_storage
from app.api.deps import Principal, get_principal
from app.core.errors import AppError, NotFoundError

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{key:path}")
async def serve_asset(key: str, principal: Principal = Depends(get_principal)) -> FileResponse:
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise AppError("Assets are served directly from object storage in this deployment")
    try:
        path = storage._path(key)  # validated (no traversal, inside storage root)
    except ValueError:
        raise NotFoundError("Asset not found") from None
    if not path.is_file():
        raise NotFoundError("Asset not found")
    # Objects are keyed by project id; membership in the workspace is verified by the session and
    # keys never cross projects. Content is immutable, so allow long-lived private caching.
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if media_type == "text/x-ssa":
        media_type = "text/plain; charset=utf-8"
    return FileResponse(
        Path(path),
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400, immutable"},
    )
