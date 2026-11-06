"""Print the exact payload the visual agent sends, and replay it against the gateway."""

from __future__ import annotations

import asyncio
import json

import httpx
from sqlalchemy import select

from app.adapters.http import default_client
from app.container import ProviderFactory
from app.core.crypto import get_vault
from app.db.session import SessionFactory
from app.models import AiProvider, Channel
from app.services.credentials import aad_for


async def main() -> None:
    async with SessionFactory() as session:
        channel = await session.scalar(select(Channel))
        ctx = await ProviderFactory(session).build_context(
            agent_key="visual_generation", workspace_id=channel.workspace_id, channel=channel
        )
        provider = ctx.params.get("provider_row")
        print("provider:", provider.name, "| base:", provider.base_url, "| model:", ctx.model)
        print("extra:", provider.extra_config)
        key = get_vault().open(provider.credential_ciphertext, aad=aad_for(provider))["api_key"]

        payload = {
            "model": ctx.model,
            "prompt": "A tiny green turtle with a red scarf on a forest path, gouache",
            "n": 1,
            "size": "auto",
            "quality": "auto",
            "background": "auto",
            "image_detail": "high",
            "output_format": "png",
        }
        print("payload:", json.dumps(payload)[:200])
        async with default_client(180) as client:
            resp = await client.post(
                f"{provider.base_url}/images/generations",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
        print("status:", resp.status_code)
        print("body:", resp.text[:600])


if __name__ == "__main__":
    asyncio.run(main())
