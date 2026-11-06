"""Verify the Temporal backend: start a run via HTTP, wait for the approval gate, then inspect history.

Usage: python scripts/smoke_temporal.py http://127.0.0.1:8002/api/v1
"""

from __future__ import annotations

import asyncio
import sys
import time

import httpx
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client


async def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8002/api/v1"
    async with httpx.AsyncClient(base_url=base, timeout=60) as client:
        r = await client.post("/auth/login", json={"email": "admin@factory.app", "password": "factory-admin-2026"})
        r.raise_for_status()
        token = client.cookies.get("factory_session")
        h = {"authorization": f"Bearer {token}"}
        channel = (await client.get("/channels", headers=h)).json()[0]
        start = await client.post(f"/workflows?channel_id={channel['id']}&force_approval=true", headers=h)
        start.raise_for_status()
        wf = start.json()
        print("workflow", wf["workflow_key"])

        deadline = time.time() + 300
        detail: dict = {}
        while time.time() < deadline:
            detail = (await client.get(f"/workflows/{wf['id']}", headers=h)).json()
            print(f"  {detail['status']:<20} {detail['stage']:<20} {detail['progress']}%")
            if detail["status"] in ("awaiting_approval", "failed", "published"):
                break
            time.sleep(4)
        if detail.get("status") != "awaiting_approval":
            print("FAILED:", detail.get("error_message"))
            return 1
        tasks = (await client.get(f"/workflows/{wf['id']}", headers=h)).json()["tasks"]
        print(f"  db tasks recorded: {len(tasks)}")

    tclient = await Client.connect("127.0.0.1:7233")
    handle = tclient.get_workflow_handle(f"factory-{wf['id']}")
    desc = await handle.describe()
    history = await handle.fetch_history()
    names = [
        e.activity_task_scheduled_event_attributes.activity_type.name
        for e in history.events
        if e.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
    ]
    print("temporal status:", desc.status.name, "| activities:", names)
    ok = desc.status.name == "RUNNING" and len(names) >= 8
    print("OK" if ok else "UNEXPECTED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
