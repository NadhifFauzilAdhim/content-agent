"""End-to-end production check: a workflow run must narrate through the unified TTS service and
record provider/model/voice metadata on every audio asset plus a usage row.

Run against a live API (default http://127.0.0.1:8001) with the worker running.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.request
import uuid

BASE = os.environ.get("API_URL", "http://127.0.0.1:8001/api/v1")
EMAIL = os.environ.get("ADMIN_EMAIL", "admin@factory.app")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "factory-admin-2026")


def call(method: str, path: str, body: dict | None = None, token: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("content-type", "application/json")
    if token:
        # The session cookie authenticates the browser; the script passes it as a bearer token.
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for header, value in resp.headers.items():
                if header.lower() == "set-cookie" and value.startswith("factory_session="):
                    cookie["factory_session"] = value.split(";")[0].split("=", 1)[1]
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


cookie: dict[str, str] = {}


def main() -> int:
    status, data = call("POST", "/auth/login", {"email": EMAIL, "password": PASSWORD})
    assert status == 200, (status, data)
    token = cookie.get("factory_session") if cookie else ""
    if not token:
        print("login did not set the session cookie")
        return 2

    status, channel = call("GET", "/channels", token=token)
    channel_id = channel[0]["id"]

    # make sure the global default is a deterministic, free provider for this check
    call("PUT", "/tts/settings", {"provider": "mock", "model": "mock-tts",
                                  "voice_id": "mock-child", "language": "en",
                                  "output_format": "wav/22050/pcm_s16le"}, token=token)

    status, wf = call("POST", f"/workflows?channel_id={channel_id}&force_approval=true", token=token)
    if status not in (200, 201):
        print("could not start workflow:", status, wf)
        return 1
    workflow_id = wf["id"]
    print("workflow", workflow_id)

    deadline = time.time() + 240
    state = wf
    while time.time() < deadline:
        status, state = call("GET", f"/workflows/{workflow_id}", token=token)
        label = f"{state.get('status')} · {state.get('stage')} · {state.get('progress')}%"
        print(" ", label)
        if state.get("status") in ("awaiting_approval", "failed", "published", "cancelled"):
            break
        time.sleep(4)

    if state.get("status") != "awaiting_approval":
        print("unexpected end state:", state.get("status"), state.get("error_message"))
        return 1

    project_id = state.get("project_id")
    status, project = call("GET", f"/content/{project_id}", token=token)
    audio = [s for s in (project.get("scenes") or []) if s.get("audio_url")]
    print(f"scenes: {len(project.get('scenes') or [])} · narrated: {len(audio)}")
    for s in audio[:5]:
        print(f"  scene {s['index']} · {s.get('audio_provider')} · {s.get('audio_model')} · "
              f"{s.get('audio_voice_id')} · {s.get('audio_duration_s')}s")
    assert audio, "no narration was stored"
    assert all(s.get("audio_provider") == "mock" for s in audio), "provider not recorded"
    assert all(s.get("audio_voice_id") == "mock-child" for s in audio), "configured voice not inherited"

    status, usage = call("GET", "/tts/usage?days=1", token=token)
    print("tts usage generations:", usage["totals"]["generations"], "chars:", usage["totals"]["characters"])
    status, gens = call("GET", "/tts/generations?limit=5", token=token)
    print("recent generations:", [(g["provider"], g["trigger"]) for g in gens["items"]])
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
