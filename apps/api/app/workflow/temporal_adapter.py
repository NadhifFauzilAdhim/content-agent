"""Temporal workflow + activities (module level, importable by the sandboxed worker).

``WORKFLOW_BACKEND=temporal`` routes productions to a real Temporal cluster. Each stage is an
activity that opens its own DB session and resumes the *same* ``ProductionPipeline`` used by the
local runner, so behaviour cannot drift between backends.

Design notes
------------
* The pipeline persists stage/progress on ``production_workflows`` after every activity, so a
  Temporal retry is safe: completed stages are detected and skipped.
* The workflow terminates at the approval gate. The approval endpoint (HTTP) then publishes
  directly — there is no dangling ``wait_condition`` that could never be signalled.
* Retry policy is exponential with a bounded attempt count; configuration errors are non-retryable.

Run the worker:  python -m app.worker
Local cluster:   docker compose --profile temporal up -d
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from app.core.logging import get_logger
from app.core.settings import get_settings

log = get_logger("factory.workflow.temporal")

STAGES = (
    "planning",
    "script_generation",
    "storyboarding",
    "voice_generation",
    "visual_generation",
    "rendering",
    "quality_checking",
    "seo",
)

NON_RETRYABLE = [
    "ProviderNotConfiguredError",
    "BudgetExceededError",
    "NotFoundError",
    "ValidationAppError",
]

def temporal_enabled() -> bool:
    return get_settings().workflow_backend == "temporal"


# --------------------------------------------------------------------------- activities


@activity.defn(name="factory_run_stage")
async def run_stage_activity(workflow_id: str, stage: str) -> dict:
    """Run one stage by resuming the pipeline up to that stage boundary (idempotent)."""
    from app.db.session import session_scope
    from app.models import ProductionWorkflow
    from app.workflow.pipeline import ApprovalPending, ProductionPipeline

    async with session_scope() as session:
        row = await session.get(ProductionWorkflow, uuid.UUID(workflow_id))
        if row is None:
            return {"status": "missing"}
        if row.status == "cancelled":
            return {"status": "cancelled"}
        pipeline = ProductionPipeline(session)
        try:
            await pipeline.resume_until(row, stage)
        except ApprovalPending:
            await session.commit()
            return {"status": "awaiting_approval"}
        await session.commit()
        return {"status": "ok", "stage": stage}


@activity.defn(name="factory_publish")
async def publish_activity(workflow_id: str) -> dict:
    from app.db.session import session_scope
    from app.workflow.pipeline import ProductionPipeline

    async with session_scope() as session:
        pipeline = ProductionPipeline(session)
        status = await pipeline.resume_after_approval(uuid.UUID(workflow_id))
        return {"status": status}


# --------------------------------------------------------------------------- workflow


@workflow.defn(name="ProductionWorkflow")
class ProductionWorkflow:
    def __init__(self) -> None:
        self._approved = False
        self._cancelled = False
        self._note: str | None = None

    @workflow.signal
    def approve(self, note: str | None = None) -> None:
        self._approved = True
        self._note = note

    @workflow.signal
    def cancel(self) -> None:
        self._cancelled = True

    @workflow.query
    def state(self) -> str:
        if self._cancelled:
            return "cancelled"
        if self._approved:
            return "approved"
        return "running"

    @workflow.run
    async def run(self, workflow_id: str, stop_at_approval: bool = True) -> str:
        policy = RetryPolicy(
            initial_interval=timedelta(seconds=5),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(minutes=5),
            maximum_attempts=3,
            non_retryable_error_types=NON_RETRYABLE,
        )
        for stage in STAGES:
            if self._cancelled:
                return "cancelled"
            result = await workflow.execute_activity(
                run_stage_activity,
                args=[workflow_id, stage],
                start_to_close_timeout=timedelta(minutes=30),
                heartbeat_timeout=timedelta(minutes=5),
                retry_policy=policy,
            )
            if result.get("status") in ("awaiting_approval", "cancelled", "missing"):
                # Park at the human gate. The approval endpoint signals `approve` (publishing is
                # executed there) or `cancel`, so the execution ends with an accurate status.
                await workflow.wait_condition(lambda: self._approved or self._cancelled)
                return "approved" if self._approved else "cancelled"
        if not stop_at_approval:
            return "stages_complete"
        await workflow.wait_condition(lambda: self._approved or self._cancelled)
        return "approved" if self._approved else "cancelled"


# --------------------------------------------------------------------------- worker


async def run_worker() -> None:
    from temporalio.client import Client
    from temporalio.worker import Worker
    from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

    settings = get_settings()
    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[ProductionWorkflow],
        activities=[run_stage_activity, publish_activity],
        workflow_runner=SandboxedWorkflowRunner(
            restrictions=SandboxRestrictions.default.with_passthrough_modules("app")
        ),
    )
    log.info("temporal worker listening on queue %s", settings.temporal_task_queue)
    await worker.run()


async def submit_temporal(workflow_id: str) -> str | None:
    """Start a Temporal execution for a workflow row. Returns handle id or None if unavailable."""
    from temporalio.client import Client

    settings = get_settings()
    try:
        client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
        handle = await client.start_workflow(
            ProductionWorkflow.run,
            args=[workflow_id, True],
            id=f"factory-{workflow_id}",
            task_queue=settings.temporal_task_queue,
        )
        log.info("temporal execution started %s", handle.id)
        return handle.id
    except Exception as exc:  # noqa: BLE001 - degrade to the local durable runner
        log.warning("temporal unavailable, using local runner: %s", exc)
        return None


async def signal_approval(workflow_id: str, note: str | None = None) -> bool:
    from temporalio.client import Client

    settings = get_settings()
    try:
        client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
        await client.get_workflow_handle(f"factory-{workflow_id}").signal(ProductionWorkflow.approve, note)
        return True
    except Exception:  # noqa: BLE001 - signal is best-effort; HTTP publish path is authoritative
        return False


async def signal_cancel(workflow_id: str) -> bool:
    from temporalio.client import Client

    settings = get_settings()
    try:
        client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
        await client.get_workflow_handle(f"factory-{workflow_id}").signal(ProductionWorkflow.cancel)
        return True
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "STAGES",
    "ProductionWorkflow",
    "publish_activity",
    "run_stage_activity",
    "run_worker",
    "signal_approval",
    "signal_cancel",
    "submit_temporal",
    "temporal_enabled",
]
