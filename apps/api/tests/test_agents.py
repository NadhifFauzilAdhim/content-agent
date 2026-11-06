"""Unit tests: structured output runner, QC rules, adapters, storage safety."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.adapters.llm import MockLLMProvider
from app.adapters.storage import _validate_key
from app.agents.base import AgentContext
from app.agents.contracts import ContentBrief, PlannerInput
from app.agents.generation import ContentPlannerAgent
from app.agents.quality import QcInput, QualityControlAgent
from app.ports.interfaces import LLMResult, Message, Usage

BRIEF = {
    "title": "The Cloud That Learned to Rain",
    "topic": "sharing",
    "angle": "A cloud learns why rain matters",
    "audience": "Children 3-7",
    "brief": "A small cloud refuses to rain until it sees a wilting garden; it learns that sharing "
             "water helps everything grow. Calm, gentle, happy ending.",
    "creative_direction": "Soft watercolour, pastel sky",
    "category": "educational",
    "estimated_duration_s": 180,
    "safety_notes": [],
    "rationale": "Teaches sharing without conflict.",
}


class FixesSchema:
    name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, model, messages, temperature=0.7, max_tokens=4096,
                       json_schema=None, timeout_s=120.0) -> LLMResult:
        self.calls += 1
        content = '{"title": "broken"' if self.calls == 1 else json.dumps(BRIEF)
        return LLMResult(content=content, usage=Usage(provider="flaky", model=model, input_tokens=10,
                                                      output_tokens=10))

    async def health(self):
        return True, "ok"


def test_planner_returns_validated_contract():
    ctx = AgentContext(workspace_id=None, llm=MockLLMProvider({"ContentBrief": BRIEF}), model="mock")  # type: ignore[arg-type]
    result = asyncio.run(
        ContentPlannerAgent().run(
            ctx,
            PlannerInput(channel_name="LL", niche="kids", audience="Children 3-7", language="en"),
        )
    )
    assert isinstance(result.output, ContentBrief)
    assert result.output.category == "educational"
    assert "mock" in " ".join(result.warnings)


def test_structured_runner_repairs_invalid_json_once():
    ctx = AgentContext(workspace_id=None, llm=FixesSchema(), model="m")  # type: ignore[arg-type]
    provider = ctx.llm
    result = asyncio.run(
        ContentPlannerAgent().run(
            ctx, PlannerInput(channel_name="LL", niche="kids", audience="kids", language="en")
        )
    )
    assert result.output.title.startswith("The Cloud")
    assert provider.calls == 2  # type: ignore[attr-defined]


def test_system_prompt_template_renders_payload():
    agent = ContentPlannerAgent()
    ctx = AgentContext(workspace_id=None, params={"banned": "violence"})  # type: ignore[arg-type]
    text = agent.render_system(
        ctx, PlannerInput(channel_name="LL", niche="kids", audience="ages 3-7", language="en",
                          target_duration_s=120)
    )
    assert "LL" in text and "ages 3-7" in text and "{channel_name}" not in text


def _qc_payload(**overrides):
    base = dict(
        title="T",
        audience="Children 3-7",
        language="en",
        made_for_kids=True,
        min_score=85,
        script_text="The sun went down. Pip walked home. Mossy lit a lantern. Pip smiled and slept.",
        scene_count=2,
        scenes=[{"index": 1}, {"index": 2}],
        image_checks=[{"index": 1, "present": True, "bytes": 5000, "width": 1920, "height": 1080},
                      {"index": 2, "present": True, "bytes": 5000, "width": 1920, "height": 1080}],
        audio_checks=[{"index": 1, "present": True, "duration_s": 3.0},
                      {"index": 2, "present": True, "duration_s": 3.0}],
        render={"present": True, "duration_s": 6.0, "bytes": 500_000, "width": 1920, "height": 1080},
        subtitle_chars=70,
        word_count=70,
        llm_review_enabled=False,
    )
    base.update(overrides)
    return QcInput(**base)


def test_qc_pass_for_clean_package():
    ctx = AgentContext(workspace_id=None)  # type: ignore[arg-type]
    result = asyncio.run(QualityControlAgent().run(ctx, _qc_payload()))
    assert result.output.approval_status == "pass"
    assert result.output.score > 90


def test_qc_flags_known_ip_and_requests_script_regeneration():
    ctx = AgentContext(workspace_id=None)  # type: ignore[arg-type]
    payload = _qc_payload(script_text="Peppa Pig jumps in mud. The sun went down.")
    result = asyncio.run(QualityControlAgent().run(ctx, payload))
    assert result.output.approval_status == "fail"
    assert "script" in result.output.regenerate
    assert any(i.area == "copyright" for i in result.output.issues)


def test_qc_missing_scene_image_targets_only_that_scene():
    ctx = AgentContext(workspace_id=None)  # type: ignore[arg-type]
    payload = _qc_payload(image_checks=[{"index": 1, "present": True, "bytes": 5000},
                                        {"index": 2, "present": False, "bytes": 0}])
    result = asyncio.run(QualityControlAgent().run(ctx, payload))
    assert "scene:2:image" in result.output.regenerate
    assert "scene:1:image" not in result.output.regenerate
    assert result.output.approval_status in ("fail", "review")


def test_storage_key_validation_blocks_traversal():
    for bad in ("../etc/passwd", "a/../../b", "a\\b", "", "/"):
        with pytest.raises(ValueError):
            _validate_key(bad)
    assert _validate_key("/p/x/y.png") == "p/x/y.png"


@pytest.mark.parametrize("text", ["no json here", "```json\n{}\n```", "prefix { } suffix"])
def test_extract_json_tolerates_noise(text):
    from app.agents.runner import extract_json

    cleaned = extract_json(text)
    assert cleaned.startswith("{") or cleaned == "no json here"


__all__ = ["Message"]
