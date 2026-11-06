"""Check that a workflow parked at the approval gate terminates when signalled.

Usage: python scripts/smoke_temporal_signal.py <workflow_id>
"""

from __future__ import annotations

import asyncio
import sys

from temporalio.client import Client


async def main() -> int:
    wf_id = sys.argv[1]
    client = await Client.connect("127.0.0.1:7233")
    handle = client.get_workflow_handle(f"factory-{wf_id}")
    before = await handle.describe()
    print("before signal:", before.status.name)
    if before.status.name != "RUNNING":
        return 1
    await handle.signal("cancel")  # the workflow's own signal (not Temporal cancellation)
    result = await handle.result()
    after = await handle.describe()
    print("after signal:", after.status.name, "| result:", result)
    return 0 if after.status.name == "COMPLETED" and result == "cancelled" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
