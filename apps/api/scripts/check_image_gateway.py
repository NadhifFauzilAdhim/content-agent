"""Live check of the gateway's image endpoint with a custom model id."""

import asyncio
from pathlib import Path

from sqlalchemy import select

from app.adapters.images import OpenAIImage
from app.core.crypto import get_vault
from app.db.session import SessionFactory
from app.models import AiProvider
from app.services.credentials import aad_for


async def main() -> None:
    vault = get_vault()
    async with SessionFactory() as session:
        rows = list(
            (await session.execute(select(AiProvider).where(AiProvider.kind == "llm"))).scalars()
        )
        gateway = next((r for r in rows if r.slug == "openai-compatible"), None)
        if gateway is None:
            print("no gateway provider configured")
            return
        key = vault.open(gateway.credential_ciphertext, aad=aad_for(gateway))["api_key"]
        base = gateway.base_url
        print("gateway:", base)

    adapter = OpenAIImage(
        key,
        base,
        options={
            "size": "auto",
            "quality": "auto",
            "background": "auto",
            "image_detail": "high",
            "output_format": "png",
        },
        label="9router",
    )
    ok, detail = await adapter.health()
    print("health:", ok, "-", detail)

    models = await adapter.list_models(refresh=True)
    image_models = [m["id"] for m in models if "image" in m["id"].lower()]
    print(f"models listed: {len(models)} (image-ish: {len(image_models)})")
    print("  sample:", ", ".join(image_models[:6]) or "-")

    result = await adapter.generate(
        prompt="A cute cat wearing a hat, soft storybook gouache illustration",
        model="ag/gemini-3.1-flash-image",
        aspect_ratio="16:9",
    )
    print(
        f"generated: {result.width}x{result.height} {result.mime} "
        f"{len(result.data) // 1024} KB model={result.usage.model} "
        f"{result.usage.latency_ms} ms"
    )
    out = Path("C:/Users/Asus/AppData/Local/Temp/opencode/cat.png")
    await asyncio.to_thread(out.write_bytes, result.data)
    print("saved:", out)


if __name__ == "__main__":
    asyncio.run(main())
