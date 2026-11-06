"""Remove providers the operator never configured (no stored key), keeping every configured one.

A provider is kept when it holds a credential, is referenced by an agent binding, or has usage
history. Everything else (unused catalogue placeholders and mocks) is deleted.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.db.session import SessionFactory
from app.models import AgentConfiguration, AiProvider, AiUsageLog
from app.services.credentials import invalidate


async def main() -> None:
    async with SessionFactory() as session:
        rows = list((await session.execute(select(AiProvider))).scalars())
        removed: list[str] = []
        kept: list[str] = []
        for provider in rows:
            bound = await session.scalar(
                select(func.count(AgentConfiguration.id)).where(
                    (AgentConfiguration.provider_id == provider.id)
                    | (AgentConfiguration.fallback_provider_id == provider.id)
                )
            )
            used = await session.scalar(
                select(func.count(AiUsageLog.id)).where(AiUsageLog.provider_id == provider.id)
            )
            has_key = bool(provider.credential_ciphertext)
            label = f"{provider.kind}/{provider.slug}"
            if has_key or bound or used:
                reason = "key" if has_key else ("bound" if bound else "usage")
                kept.append(f"{label} ({reason})")
                continue
            invalidate(provider.id)
            await session.delete(provider)
            removed.append(label)

        # Table-level FK is SET NULL; clear bindings pointing at providers we just deleted.
        await session.execute(
            AgentConfiguration.__table__.update().where(
                AgentConfiguration.provider_id.not_in(select(AiProvider.id))
            ).values(provider_id=None)
        )
        await session.execute(
            AgentConfiguration.__table__.update().where(
                AgentConfiguration.fallback_provider_id.not_in(select(AiProvider.id))
            ).values(fallback_provider_id=None)
        )
        await session.commit()

    print("removed:", ", ".join(removed) or "none")
    print("kept:   ", ", ".join(kept) or "none")


if __name__ == "__main__":
    asyncio.run(main())
