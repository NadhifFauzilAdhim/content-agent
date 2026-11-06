"""Agent I/O contracts.

These models are the single source of truth for agent structured outputs. The JSON schema of
each output model is what gets sent to the LLM (OpenAI ``json_schema`` / Gemini
``responseSchema``) and what every response is validated against.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Transition = Literal["cut", "fade", "slide", "zoom"]
Severity = Literal["info", "warning", "error", "critical"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --------------------------------------------------------------------------- planner


class PlannerInput(Contract):
    channel_name: str
    niche: str
    audience: str
    language: str
    recent_titles: list[str] = Field(default_factory=list)
    target_duration_s: int = 240
    category_hint: str | None = None
    banned_topics: list[str] = Field(default_factory=list)
    performance_notes: list[str] = Field(default_factory=list)


class ContentBrief(Contract):
    title: str = Field(min_length=4, max_length=120)
    topic: str = Field(min_length=3, max_length=120)
    angle: str
    audience: str
    brief: str = Field(min_length=40)
    creative_direction: str
    category: Literal["story", "educational", "song", "rhyme", "how-to", "lullaby"]
    estimated_duration_s: int = Field(ge=60, le=900)
    safety_notes: list[str] = Field(default_factory=list)
    rationale: str


# --------------------------------------------------------------------------- script


class ScriptBrief(Contract):
    title: str
    topic: str
    brief: str
    creative_direction: str
    audience: str
    language: str
    target_duration_s: int
    character_names: list[str] = Field(default_factory=list)
    guidelines: str | None = None


class DialogueLine(Contract):
    character: str
    line: str
    emotion: str | None = None


class ScriptScene(Contract):
    index: int = Field(ge=1)
    title: str
    narration: str
    dialogue: list[DialogueLine] = Field(default_factory=list)
    duration_s: int = Field(ge=2, le=45)
    visual_instruction: str
    sfx: list[str] = Field(default_factory=list)
    transition: Transition = "fade"

    @field_validator("narration")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("narration must not be empty")
        return v


class ScriptDraft(Contract):
    title: str = Field(min_length=4, max_length=120)
    description: str
    hook: str
    scenes: list[ScriptScene] = Field(min_length=3)
    moral: str | None = None
    target_age: str | None = None

    @property
    def narration(self) -> str:
        return "\n\n".join(s.narration for s in self.scenes)


# --------------------------------------------------------------------------- storyboard


class StoryboardInput(Contract):
    title: str
    style: str
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    characters: list[dict] = Field(default_factory=list)
    palette: list[str] = Field(default_factory=list)
    scenes: list[ScriptScene]


class StoryboardScene(Contract):
    index: int = Field(ge=1)
    camera: str
    composition: str
    characters: list[str] = Field(default_factory=list)
    background: str
    action: str
    image_prompt: str = Field(min_length=20)
    negative_prompt: str
    sfx: list[str] = Field(default_factory=list)
    duration_s: int = Field(ge=2, le=45)
    transition: Transition = "fade"


class StoryboardDraft(Contract):
    style_guide: str
    scenes: list[StoryboardScene] = Field(min_length=3)


# --------------------------------------------------------------------------- seo


class SeoInput(Contract):
    title: str
    description: str
    narration: str
    audience: str
    language: str
    channel_name: str
    niche: str
    made_for_kids: bool = True


class MetadataDraft(Contract):
    title: str = Field(min_length=10, max_length=100)
    description: str = Field(min_length=80)
    tags: list[str] = Field(min_length=5, max_length=30)
    thumbnail_text: str = Field(min_length=2, max_length=40)
    thumbnail_concept: str
    thumbnail_prompt: str
    playlist: str
    made_for_kids: bool = True
    category: str = "Education"


# --------------------------------------------------------------------------- qc


class QcCheck(Contract):
    id: str
    label: str
    passed: bool
    weight: float = Field(ge=0, le=1)
    note: str


class QcIssue(Contract):
    severity: Severity
    area: Literal["script", "storyboard", "audio", "visual", "video", "subtitles", "policy", "copyright"]
    message: str
    scene_index: int | None = None
    regenerate: list[str] = Field(default_factory=list)


class QualityReport(Contract):
    score: float = Field(ge=0, le=100)
    approval_status: Literal["pass", "review", "fail"]
    checks: list[QcCheck]
    issues: list[QcIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    regenerate: list[str] = Field(default_factory=list)


class ContentSafetyReview(Contract):
    age_appropriate: bool
    policy_flags: list[str] = Field(default_factory=list)
    tone_notes: str
    summary: str


# --------------------------------------------------------------------------- analytics


class AnalyticsWindow(Contract):
    channel_name: str
    period_days: int
    videos: list[dict] = Field(default_factory=list)
    top_topics: list[str] = Field(default_factory=list)
