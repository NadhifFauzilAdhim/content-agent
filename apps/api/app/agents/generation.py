"""Content Planner, Script Writer, Storyboard and SEO — declarative LLM agents."""

from __future__ import annotations

import json
import re

from app.agents.base import AgentContext, AgentResult
from app.agents.contracts import (
    ContentBrief,
    MetadataDraft,
    PlannerInput,
    ScriptBrief,
    ScriptDraft,
    SeoInput,
    StoryboardDraft,
    StoryboardInput,
)
from app.agents.runner import StructuredRunner
from app.ports.interfaces import Usage

PLANNER_SYSTEM = """You are the Content Planner for {channel_name}, a {niche} channel for {audience}.
You propose ONE original, non-repetitive content idea per run.

Rules:
- Never repeat or lightly rephrase a recent title.
- Must be safe and age-appropriate for {audience}; avoid {banned}.
- Prefer original stories and clear educational value over derivative content.
- Target length: {duration} seconds of narration.
- Return a JSON object matching the schema exactly. No prose outside JSON."""

SCRIPT_SYSTEM = """You are the Script Writer for an original {niche} channel ({audience}).
Write a complete, engaging script with scene breaks.

Rules:
- Original writing only. No known-IP characters, song lyrics, or trademarked names.
- Warm, simple language appropriate for the audience; short sentences.
- Structure: hook (first 10 seconds), rising action, gentle climax, satisfying ending, calm send-off.
- Each scene: 1-3 sentences of narration, optional short dialogue, and a concrete visual instruction.
- Total narration should fit ~{duration} seconds (about 2.6 words per second).
- Avoid scary, violent, or unsafe content. No instructions for dangerous activities.
- Return ONLY JSON matching the schema."""

STORYBOARD_SYSTEM = """You are a Storyboard Artist and Art Director for {niche} content ({audience}).
Convert the script into a shot-by-shot storyboard with a consistent art direction.

Art direction: {style}. Palette: {palette}.
Characters (locked appearance — always restate their defining visual traits in every prompt):
{characters}

Rules:
- One storyboard scene per script scene, same index.
- image_prompt must be self-contained, describe the shot, character appearance, setting, lighting
  and mood; no text in image; no watermark.
- negative_prompt: "text, watermark, signature, extra limbs, horror, weapons, scary imagery".
- Return ONLY JSON matching the schema."""

SEO_SYSTEM = """You are the SEO & Metadata specialist for {channel_name} ({niche}).
Create metadata that is accurate to the video, compelling, non-clickbait, and policy-safe.

Rules:
- Title <= 100 characters, front-load the searchable topic, no ALL CAPS, no excessive emoji.
- Description: 2-4 sentences, then a short call to action; never claim untruthful benefits.
- Tags: 8-15 lowercase search phrases relevant to parents who search for this content.
- Thumbnail text: <= 6 words. Thumbnail concept must be describable and readable at small size.
- Made for kids: {made_for_kids}.
- Return ONLY JSON matching the schema."""


def _render(template: str, **values: object) -> str:
    out = template
    for key in sorted(values, key=len, reverse=True):
        out = out.replace("{" + key + "}", str(values[key]))
    return out


class LLMAgent:
    """Generic declarative agent: schema in, schema out, usage logged."""

    key = "llm_agent"
    name = "LLM Agent"

    def __init__(self, *, system_prompt: str, user_builder) -> None:  # type: ignore[no-untyped-def]
        self.system_prompt = system_prompt
        self.user_builder = user_builder

    def render_system(self, ctx: AgentContext, payload: object) -> str:
        """Fill template placeholders from the payload and context parameters."""
        values: dict[str, object] = ctx.params.copy()
        if hasattr(payload, "model_dump"):
            values.update(payload.model_dump())  # type: ignore[union-attr]
            data = payload.model_dump()  # type: ignore[union-attr]
            if isinstance(data.get("characters"), list):
                values["characters"] = "\n".join(
                    f"- {c.get('name')}: {c.get('visual_prompt') or c.get('description')}"
                    if isinstance(c, dict) else str(c)
                    for c in data["characters"]
                )
            if isinstance(data.get("palette"), list):
                values["palette"] = ", ".join(map(str, data["palette"]))
            if isinstance(data.get("banned_topics"), list):
                values["banned"] = ", ".join(map(str, data["banned_topics"])) or "nothing specific"
        values.setdefault("banned", "nothing specific")
        return _render(self.system_prompt, **values)

    async def run(self, ctx: AgentContext, payload):  # type: ignore[no-untyped-def]
        provider = ctx.require_llm()
        runner = StructuredRunner(provider)
        result, usage = await runner.run(
            model=ctx.model or "default",
            system=ctx.system_prompt or self.render_system(ctx, payload),
            user=self.user_builder(payload),
            output_model=self.OutputModel,
            temperature=ctx.temperature,
            max_tokens=ctx.max_tokens,
        )
        return AgentResult(
            output=result,
            usage=usage,
            provider=usage.provider,
            model=usage.model,
            warnings=["Generated by a mock provider — configure a real LLM for production."]
            if usage.provider == "mock"
            else [],
        )


class ContentPlannerAgent(LLMAgent):
    key = "content_planner"
    name = "Content Planner"
    InputModel = PlannerInput
    OutputModel = ContentBrief

    def __init__(self) -> None:
        super().__init__(
            system_prompt=PLANNER_SYSTEM,
            user_builder=lambda p: json.dumps(p.model_dump(), ensure_ascii=False),
        )


class ScriptWriterAgent(LLMAgent):
    key = "script_writer"
    name = "Script Writer"
    InputModel = ScriptBrief
    OutputModel = ScriptDraft

    def __init__(self) -> None:
        super().__init__(
            system_prompt=SCRIPT_SYSTEM,
            user_builder=lambda p: json.dumps(p.model_dump(), ensure_ascii=False),
        )


class StoryboardAgent(LLMAgent):
    key = "storyboard"
    name = "Storyboard"
    InputModel = StoryboardInput
    OutputModel = StoryboardDraft

    def __init__(self) -> None:
        super().__init__(
            system_prompt=STORYBOARD_SYSTEM,
            user_builder=lambda p: json.dumps(p.model_dump(), ensure_ascii=False),
        )


class SeoAgent(LLMAgent):
    key = "seo_metadata"
    name = "SEO & Metadata"
    InputModel = SeoInput
    OutputModel = MetadataDraft

    def __init__(self) -> None:
        super().__init__(
            system_prompt=SEO_SYSTEM,
            user_builder=lambda p: json.dumps(p.model_dump(), ensure_ascii=False),
        )


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def usage_zero() -> Usage:
    return Usage(provider="rules", model="deterministic", operation="rules", units=1, unit_label="check")
