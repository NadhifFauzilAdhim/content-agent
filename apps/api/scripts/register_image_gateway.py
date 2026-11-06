"""Register the operator's OpenAI-compatible image provider using the gateway key already stored.

The key is read from the encrypted vault (never printed) and reused so the operator does not have
to paste it twice. Runs through the same code path as the form.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.core.crypto import get_vault
from app.db.session import SessionFactory
from app.models import AiProvider, Workspace
from app.services.credentials import CredentialService, aad_for

IMAGE_MODEL = "ag/gemini-3.1-flash-image"
OPTIONS = {
    "size": "auto",
    "quality": "auto",
    "background": "auto",
    "image_detail": "high",
    "output_format": "png",
}


async def main() -> None:
    vault = get_vault()
    async with SessionFactory() as session:
        rows = list(
            (
                await session.execute(
                    select(AiProvider).where(
                        AiProvider.kind == "llm", AiProvider.slug == "openai-compatible"
                    )
                )
            ).scalars()
        )
        gateway = rows[0]
        api_key = vault.open(gateway.credential_ciphertext, aad=aad_for(gateway))["api_key"]
        base = gateway.base_url
        workspace_id = gateway.workspace_id

        existing = await session.scalar(
            select(AiProvider).where(
                AiProvider.workspace_id == workspace_id,
                AiProvider.kind == "image",
                AiProvider.slug == "openai-compatible",
            )
        )
        if existing is not None:
            existing.name = "9router images"
            existing.base_url = base
            existing.models = [{"id": IMAGE_MODEL}]
            existing.extra_config = OPTIONS
            existing.is_enabled = True
            provider = existing
            print("updated existing image provider")
        else:
            provider = AiProvider(
                workspace_id=workspace_id,
                kind="image",
                slug="openai-compatible",
                name="9router images",
                vendor="9router",
                base_url=base,
                models=[{"id": IMAGE_MODEL}],
                extra_config=OPTIONS,
                is_mock=False,
                is_enabled=True,
                health="unknown",
            )
            session.add(provider)
            await session.flush()
            print("created image provider")

        await CredentialService(session).set_credentials(
            provider, {"api_key": api_key}, action="provider.credentials.updated"
        )
        await session.commit()
        print(f"provider {provider.id} -> {base} model={IMAGE_MODEL}")
        print("options:", OPTIONS)

        workspace = await session.get(Workspace, workspace_id)
        print("workspace:", workspace.name if workspace else workspace_id)
        # sanity: the id must round-trip
        uuid.UUID(str(provider.id))


if __name__ == "__main__":
    asyncio.run(main())
