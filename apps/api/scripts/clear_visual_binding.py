"""Clear the visual_generation agent binding so provider selection is automatic."""

import asyncio

from sqlalchemy import select

from app.db.session import SessionFactory
from app.models import Agent, AgentConfiguration


async def main() -> None:
    async with SessionFactory() as session:
        agent = await session.scalar(select(Agent).where(Agent.key == "visual_generation"))
        changed = 0
        for config in (
            await session.execute(
                select(AgentConfiguration).where(AgentConfiguration.agent_id == agent.id)
            )
        ).scalars():
            if config.provider_id or config.model:
                config.provider_id = None
                config.model = None
                changed += 1
        await session.commit()
        print(f"cleared {changed} binding(s); selection now follows priority")


if __name__ == "__main__":
    asyncio.run(main())
