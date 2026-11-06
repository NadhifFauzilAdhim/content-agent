"""Object storage: local filesystem (development) and Cloudflare R2 / S3 (production)."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from app.core.settings import get_settings
from app.ports.interfaces import ProviderError, StoredObject


def _validate_key(key: str) -> str:
    key = (key or "").strip().lstrip("/")
    if not key or "\\" in key or "\x00" in key or any(part in ("..", "") for part in key.split("/")):
        raise ValueError(f"Invalid storage key: {key!r}")
    return key


class LocalStorage:
    backend = "local"

    def __init__(self, root: Path, public_base: str = "/files") -> None:
        self.root = root
        self.public_base = public_base
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = _validate_key(key)
        path = (self.root / safe).resolve()
        if not str(path).startswith(str(self.root.resolve())):
            raise ValueError("Path traversal blocked")
        return path

    async def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> StoredObject:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(write)
        return StoredObject(
            key=key,
            url=self.url_for(key),
            bytes=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
        )

    async def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return await asyncio.to_thread(path.read_bytes)

    def url_for(self, key: str) -> str:
        return f"{self.public_base}/{key.lstrip('/')}"

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    async def health(self) -> tuple[bool, str]:
        return self.root.exists(), f"Local storage · {self.root}"


class R2Storage:
    backend = "r2"

    def __init__(self) -> None:
        s = get_settings()
        if not all([s.r2_account_id, s.r2_access_key_id, s.r2_secret_access_key, s.r2_bucket]):
            raise ProviderError("R2 credentials are incomplete")
        self._bucket = s.r2_bucket
        self._base = s.r2_public_base_url or f"https://{s.r2_account_id}.r2.cloudflarestorage.com/{s.r2_bucket}"
        import boto3

        self._client = boto3.client(
            "s3",
            endpoint_url=f"https://{s.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=s.r2_access_key_id,
            aws_secret_access_key=s.r2_secret_access_key,
            region_name="auto",
        )

    async def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> StoredObject:
        key = _validate_key(key)

        def upload() -> None:
            self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

        await asyncio.to_thread(upload)
        return StoredObject(key, self.url_for(key), len(data), hashlib.sha256(data).hexdigest())

    async def get_bytes(self, key: str) -> bytes:
        def download() -> bytes:
            return self._client.get_object(Bucket=self._bucket, Key=_validate_key(key))["Body"].read()

        return await asyncio.to_thread(download)

    def url_for(self, key: str) -> str:
        return f"{self._base.rstrip('/')}/{key.lstrip('/')}"

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(
            lambda: self._client.delete_object(Bucket=self._bucket, Key=_validate_key(key))
        )

    async def health(self) -> tuple[bool, str]:
        try:
            await asyncio.to_thread(lambda: self._client.head_bucket(Bucket=self._bucket))
            return True, "R2 bucket reachable"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"


def build_storage() -> LocalStorage | R2Storage:
    s = get_settings()
    if s.storage_backend == "r2" and s.r2_bucket:
        return R2Storage()
    return LocalStorage(s.storage_root)


_storage: LocalStorage | R2Storage | None = None


def get_storage() -> LocalStorage | R2Storage:
    global _storage
    if _storage is None:
        _storage = build_storage()
    return _storage
