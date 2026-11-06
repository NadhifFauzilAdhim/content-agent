"""End-to-end smoke through the HTTP API: login → start production → await approval → approve.

Requires a running API (`uvicorn app.main:app --port 8000`). Run: python scripts/smoke_http.py
"""

from __future__ import annotations

import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/api/v1"
EMAIL = "admin@factory.app"
PASSWORD = "factory-admin-2026"


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60) as client:
        r = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        r.raise_for_status()
        token = r.cookies.get("factory_session") or client.cookies.get("factory_session")
        headers = {"authorization": f"Bearer {token}"}
        channels = client.get("/channels", headers=headers).json()
        if not channels:
            print("no channels")
            return 1
        channel = channels[0]
        print(f"channel: {channel['name']} ({len(channels)} total)")

        r = client.post(f"/workflows?channel_id={channel['id']}&force_approval=true", headers=headers)
        r.raise_for_status()
        wf = r.json()
        print(f"workflow {wf['workflow_key']} started")

        deadline = time.time() + 600
        detail = {}
        while time.time() < deadline:
            detail = client.get(f"/workflows/{wf['id']}", headers=headers).json()
            print(f"  {detail['status']:<20} {detail['stage']:<20} {detail['progress']:>3}%")
            if detail["status"] in ("awaiting_approval", "failed", "published"):
                break
            time.sleep(5)
        if detail.get("status") == "failed":
            print("FAILED:", detail.get("error_message"))
            return 1
        project = client.get(f"/content/{detail['project_id']}", headers=headers).json()
        print(f"project: {project['title']} · scenes={len(project['scenes'])} · qc={project['qc']['score'] if project['qc'] else None}")
        print(f"render: {project['renders'][0]['url'] if project['renders'] else None}")
        approvals = client.get("/approvals", headers=headers).json()
        print(f"pending approvals: {len(approvals)}")
        overview = client.get("/overview", headers=headers).json()
        print("totals:", {k: v["value"] for k, v in overview["totals"].items()})
        costs = client.get("/costs", headers=headers).json()
        print(f"cost month: ${costs['month_usd']}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
