"""Envelope encryption for provider credentials and OAuth tokens.

Secrets are sealed with **AES-256-GCM** (an authenticated cipher) using a single master key that
never lives in the database:

* ``APP_ENCRYPTION_KEY`` — preferred source. Accepts a 32-byte key as 64 hex characters or as
  urlsafe base64 (that is also the legacy Fernet format, so existing keys keep working).
* ``CREDENTIAL_KEY`` — legacy/short name, still honoured, same formats.

Each record is sealed with its own random 96-bit nonce and carries the record's identity as
GCM additional data, so a ciphertext cannot be transplanted onto another provider or workspace.
The database only ever stores ``ciphertext`` plus a one-way fingerprint used for display
(e.g. ``sk-…a91f``). Plaintext secrets never leave the API process.

Blobs written by the previous Fernet-based vault are still readable and are re-sealed
transparently by :class:`app.services.credentials.CredentialService`.

Master-key problems are **never** silently downgraded to plaintext storage: a missing or invalid
key disables credential management and surfaces an explicit setup state.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import secrets
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.settings import get_settings

VERSION = "v2"
_NONCE_BYTES = 12
_KEY_BYTES = 32
# Key generation identifiers for the legacy Fernet vault (see :func:`seal` / :func:`open`).
_FERNET_PREFIX = "gAAAAA"


class CredentialError(RuntimeError):
    """Raised when a credential cannot be sealed, opened, or when the master key is unusable."""

    def __init__(self, message: str, *, code: str = "credential_error") -> None:
        super().__init__(message)
        self.code = code


def parse_master_key(raw: str) -> tuple[bytes, bool]:
    """Normalise a configured master key into 32 raw bytes.

    Returns ``(key, was_fernet)``; ``was_fernet`` is True when the key is the urlsafe-base64
    encoding produced by the old ``gen-key`` command, so legacy ciphertexts can be read.
    """
    value = (raw or "").strip()
    if not value:
        raise CredentialError(
            "APP_ENCRYPTION_KEY is not configured. Generate one with "
            "`python -m app.cli gen-key` and set it in the environment.",
            code="master_key_missing",
        )
    if len(value) == 64:
        try:
            return bytes.fromhex(value), False
        except ValueError:
            pass
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise CredentialError(
            "APP_ENCRYPTION_KEY must be 64 hex characters or 32 base64-encoded bytes",
            code="master_key_invalid",
        ) from exc
    if len(decoded) != _KEY_BYTES:
        raise CredentialError(
            f"APP_ENCRYPTION_KEY decoded to {len(decoded)} bytes; AES-256 requires exactly 32",
            code="master_key_invalid",
        )
    return decoded, value.startswith(_FERNET_PREFIX) or len(value) == 44


def generate_master_key() -> str:
    """A fresh 32-byte key, hex encoded (no shell-quoting hazards)."""
    return secrets.token_hex(_KEY_BYTES)


def _aad(aad: str) -> bytes:
    return f"factory/credentials/{VERSION}/{aad}".encode()


class CredentialVault:
    """AES-256-GCM sealing of credential dictionaries.

    ``aad`` binds a ciphertext to a scope (provider row, workspace). Use the same value when
    sealing and opening; a mismatch fails authentication instead of returning other data.
    """

    def __init__(self, key: str | bytes) -> None:
        raw, self._fernet_compatible = (key, True) if isinstance(key, bytes) else parse_master_key(key)
        self._startup_key = raw
        self._aead = AESGCM(raw)
        self._fernet = Fernet(base64.urlsafe_b64encode(raw)) if self._fernet_compatible else None
        # Retained for one release so tokens sealed by the old vault remain readable.
        self._legacy_fernet = Fernet(base64.urlsafe_b64encode(raw))

    # -- keys -------------------------------------------------------------
    @staticmethod
    def generate_key() -> str:
        return generate_master_key()

    @staticmethod
    def is_configured() -> bool:
        s = get_settings()
        return bool((s.app_encryption_key or s.credential_key or os.environ.get("APP_ENCRYPTION_KEY") or "").strip())

    # -- seal / open ------------------------------------------------------
    def seal(self, data: dict[str, Any], *, aad: str = "default") -> bytes:
        plaintext = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
        nonce = os.urandom(_NONCE_BYTES)
        blob = self._aead.encrypt(nonce, plaintext, _aad(aad))
        return VERSION.encode() + b":" + nonce + blob

    def open(self, blob: bytes, *, aad: str = "default") -> dict[str, Any]:
        if not blob:
            raise CredentialError("Credential blob is empty")
        if blob.startswith(b"v2:"):
            nonce, sealed = blob[3:3 + _NONCE_BYTES], blob[3 + _NONCE_BYTES:]
            try:
                plaintext = self._aead.decrypt(nonce, sealed, _aad(aad))
            except (InvalidTag, ValueError) as exc:
                raise CredentialError(
                    "The stored credential could not be authenticated. APP_ENCRYPTION_KEY may have "
                    "changed, or the record was sealed for a different scope.",
                    code="credential_unreadable",
                ) from exc
            return json.loads(plaintext)
        # Legacy Fernet payload (no version header, urlsafe-base64 token).
        try:
            plaintext = self._legacy_fernet.decrypt(blob).decode()
        except (InvalidToken, ValueError) as exc:
            raise CredentialError(
                "The stored credential cannot be decrypted with the current APP_ENCRYPTION_KEY.",
                code="credential_unreadable",
            ) from exc
        data = json.loads(plaintext)
        return data if isinstance(data, dict) else {"api_key": str(data)}

    def is_legacy(self, blob: bytes) -> bool:
        return bool(blob) and not blob.startswith(b"v2:")

    # -- single-value helpers (OAuth tokens and similar) ------------------
    def encrypt(self, secret: str) -> bytes:
        return self.seal({"api_key": secret})

    def decrypt(self, blob: bytes) -> str:
        return str(self.open(blob).get("api_key", ""))

    def encrypt_mapping(self, data: dict[str, Any]) -> bytes:
        return self.seal(data)

    def decrypt_mapping(self, blob: bytes) -> dict[str, Any]:
        return self.open(blob)

    # -- display ----------------------------------------------------------
    @staticmethod
    def fingerprint(secret: str) -> str:
        digest = hashlib.sha256(secret.encode()).hexdigest()
        prefix = secret[:3] if len(secret) > 6 else ""
        return f"{prefix}…{digest[-4:]}"


def get_vault() -> CredentialVault:
    settings = get_settings()
    return CredentialVault(settings.app_encryption_key or settings.credential_key)


def master_key_status() -> tuple[bool, str | None]:
    """``(ready, problem)`` — used by the API to show an explicit setup state."""
    settings = get_settings()
    raw = (settings.app_encryption_key or settings.credential_key or "").strip()
    if not raw:
        return False, "APP_ENCRYPTION_KEY is not set — credentials cannot be stored or read."
    try:
        parse_master_key(raw)
    except CredentialError as exc:
        return False, str(exc)
    return True, None
