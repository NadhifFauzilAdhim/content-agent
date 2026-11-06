"""Resume the Pip workflow from its render stage now that the video exists.

The pipeline is idempotent: re-running a stage that already produced its output reuses it.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.db.session import SessionFactory
from app.models import ProductionWorkflow, WorkflowTask

WORKFLOW_ID = uuid.UUID("91e1d33d-8481-4a2b-9eb2-24af8a8419cd")


async def main() -> None:
    async with SessionFactory() as session:
        workflow = await session.get(ProductionWorkflow, WORKFLOW_ID)
        print("before:", workflow.status, workflow.stage, "| retry", workflow.retry_count)
        for task in (
            await session.execute(
                select(WorkflowTask)
                .where(WorkflowTask.workflow_id == WORKFLOW_ID)
                .order_by(WorkflowTask.step_index)
            )
        ).scalars():
            print(f"  {task.step_index} {task.agent_key:18} {task.status}")

        # Reset the run so the pipeline can continue from where it stopped.
        workflow.status = "pending"
        workflow.error_message = None
        workflow.completed_at = None
        await session.commit()
        print("reset to pending")


if __name__ == "__main__":
    asyncio.run(main())
