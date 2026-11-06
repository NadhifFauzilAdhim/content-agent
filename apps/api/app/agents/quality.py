"""Quality Control, Publishing and Analytics agents."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, AgentError, AgentResult
from app.agents.contracts import (
    ContentSafetyReview,
    Contract,
    QcCheck,
    QcIssue,
    QualityReport,
)
from app.agents.runner import StructuredRunner
from app.ports.interfaces import UploadRequest, Usage

# --------------------------------------------------------------------------- QC

QC_WEIGHTS = {
    "script_quality": 0.20,
    "scene_consistency": 0.15,
    "assets_complete": 0.15,
    "audio_sync": 0.10,
    "subtitle_alignment": 0.05,
    "media_integrity": 0.10,
    "age_appropriateness": 0.15,
    "copyright_safety": 0.10,
}

BANNED_PHRASES = (
    "kill", "blood", "gun", "knife", "suicide", "die ", "dead body",
    "hate", "stupid", "idiot", "shut up", "hell", "damn", "scary monster eats",
)

SAFETY_SYSTEM = """You are a child-safety reviewer for a YouTube Made-for-Kids channel.
Review the script for age appropriateness. Flag: fear or violence, unsafe imitation
(e.g. dangerous stunts), commercial/persuasive pressure, personal data requests,
copyright/IP characters or songs. Approve content that is gentle, imaginative and educational.
Return ONLY JSON matching the schema."""


class QcSceneIssue(Contract):
    scene_index: int
    message: str
    areas: list[str]


class QcInput(Contract):
    title: str
    audience: str
    language: str
    made_for_kids: bool = True
    min_score: float = 85
    script_text: str
    scene_count: int
    scenes: list[dict] = Field(default_factory=list)
    image_checks: list[dict] = Field(default_factory=list)  # {index, present, bytes, width, height}
    audio_checks: list[dict] = Field(default_factory=list)  # {index, present, duration_s}
    render: dict = Field(default_factory=dict)  # {present, duration_s, bytes, width, height, ...}
    # Output inspection produced by the Remotion renderer (ffprobe-based): dimensions, fps,
    # duration, audio presence, A/V sync, faststart. See app/adapters/video.py::validate.
    render_validation: dict = Field(default_factory=dict)
    subtitle_chars: int = 0
    word_count: int = 0
    llm_review_enabled: bool = True


class QualityControlAgent:
    key = "quality_control"
    name = "Quality Control"
    InputModel = QcInput
    OutputModel = QualityReport

    async def run(self, ctx: AgentContext, payload: QcInput) -> AgentResult[QualityReport]:
        checks: list[QcCheck] = []
        issues: list[QcIssue] = []
        warnings: list[str] = []
        regenerate: set[str] = set()

        # 1. script quality — deterministic heuristics
        words = max(1, payload.word_count)
        avg_sentence = _avg_sentence_length(payload.script_text)
        script_ok = avg_sentence <= 16 and words >= 60
        checks.append(
            QcCheck(
                id="script_quality",
                label="Script readability",
                passed=script_ok,
                weight=QC_WEIGHTS["script_quality"],
                note=f"{words} words · {avg_sentence:.1f} words/sentence",
            )
        )
        if avg_sentence > 16:
            issues.append(
                QcIssue(severity="warning", area="script",
                        message="Sentences are long for the target audience.", regenerate=[])
            )

        # 2. scene consistency
        indices = [s.get("index") for s in payload.scenes]
        consistent = len(indices) == payload.scene_count and indices == list(range(1, payload.scene_count + 1))
        checks.append(
            QcCheck(
                id="scene_consistency",
                label="Scene numbering & count",
                passed=consistent,
                weight=QC_WEIGHTS["scene_consistency"],
                note=f"{len(indices)} scenes · expected {payload.scene_count}",
            )
        )
        if not consistent:
            issues.append(QcIssue(severity="error", area="storyboard",
                                  message="Storyboard scenes are missing or out of order."))

        # 3. assets complete
        missing_images = [c for c in payload.image_checks if not c.get("present") or (c.get("bytes") or 0) < 1024]
        checks.append(
            QcCheck(
                id="assets_complete",
                label="Visual assets",
                passed=not missing_images,
                weight=QC_WEIGHTS["assets_complete"],
                note=f"{len(payload.image_checks) - len(missing_images)}/{len(payload.image_checks)} present",
            )
        )
        for c in missing_images:
            issues.append(QcIssue(severity="error", area="visual",
                                  message=f"Scene {c.get('index')} image is missing or corrupt.",
                                  scene_index=c.get("index"),
                                  regenerate=[f"scene:{c.get('index')}:image"]))
            regenerate.add(f"scene:{c.get('index')}:image")

        # 4. audio sync
        missing_audio = [c for c in payload.audio_checks if not c.get("present") or (c.get("duration_s") or 0) <= 0]
        checks.append(
            QcCheck(
                id="audio_sync",
                label="Narration per scene",
                passed=not missing_audio,
                weight=QC_WEIGHTS["audio_sync"],
                note=f"{len(payload.audio_checks) - len(missing_audio)}/{len(payload.audio_checks)} voiced",
            )
        )
        for c in missing_audio:
            issues.append(QcIssue(severity="error", area="audio",
                                  message=f"Scene {c.get('index')} has no narration audio.",
                                  scene_index=c.get("index"),
                                  regenerate=[f"scene:{c.get('index')}:audio"]))
            regenerate.add(f"scene:{c.get('index')}:audio")

        # 5. subtitle alignment
        subtitle_ok = payload.subtitle_chars >= max(10, int(words * 0.6))
        checks.append(
            QcCheck(
                id="subtitle_alignment",
                label="Subtitle coverage",
                passed=subtitle_ok,
                weight=QC_WEIGHTS["subtitle_alignment"],
                note=f"{payload.subtitle_chars} subtitle chars for {words} words",
            )
        )

        # 6. media integrity — trust the renderer's own output validation when it is available
        validation_checks = list((payload.render_validation or {}).get("checks") or [])
        validated = bool(payload.render_validation) and bool(validation_checks)
        render_ok = bool(payload.render.get("present")) and (payload.render.get("bytes") or 0) > 50_000
        if validated:
            render_ok = render_ok and bool(payload.render_validation.get("passed"))
            failed = [c for c in validation_checks if not c.get("passed")]
            note = (
                f"{payload.render.get('duration_s', 0)}s · "
                f"{payload.render.get('width', 0)}x{payload.render.get('height', 0)} · "
                + ("all output checks passed" if not failed
                   else "; ".join(str(c.get("note")) for c in failed[:3]))
            )
        else:
            note = (
                f"{payload.render.get('duration_s', 0)}s · "
                f"{payload.render.get('width', 0)}x{payload.render.get('height', 0)} · "
                "unverified output (no render validation recorded)"
            )
            warnings.append("Rendered file was not inspected (dimensions, fps, audio, A/V sync).")
        checks.append(
            QcCheck(
                id="media_integrity",
                label="Rendered video",
                passed=render_ok,
                weight=QC_WEIGHTS["media_integrity"],
                note=note,
            )
        )
        if not render_ok:
            issues.append(QcIssue(severity="critical", area="video",
                                  message="Rendered video is missing, too small, or failed output validation."))

        # 7. age appropriateness — rules + optional LLM review
        lowered = payload.script_text.lower()
        flagged = [p.strip() for p in BANNED_PHRASES if p in lowered]
        safety_ok = not flagged
        safety_note = "no flagged language" if safety_ok else f"flagged: {', '.join(flagged)}"
        usage = Usage(provider="rules", model="lexicon", operation="rules", units=1, unit_label="check")
        if payload.llm_review_enabled and ctx.llm is not None:
            try:
                runner = StructuredRunner(ctx.llm)
                review, review_usage = await runner.run(
                    model=ctx.model or "default",
                    system=ctx.system_prompt or SAFETY_SYSTEM,
                    user=json.dumps(
                        {"audience": payload.audience, "made_for_kids": payload.made_for_kids,
                         "language": payload.language, "script": payload.script_text[:12000]},
                        ensure_ascii=False,
                    ),
                    output_model=ContentSafetyReview,
                    temperature=0.0,
                    max_tokens=1200,
                )
                usage = _merge(usage, review_usage)
                if not review.age_appropriate or review.policy_flags:
                    safety_ok = False
                    safety_note = "; ".join(review.policy_flags) or review.summary
                else:
                    safety_note = review.summary[:160]
            except Exception as exc:  # noqa: BLE001 - safety review failure must not pass silently
                warnings.append(f"LLM safety review unavailable ({type(exc).__name__}); lexicon only.")
        checks.append(
            QcCheck(id="age_appropriateness", label="Age appropriateness", passed=safety_ok,
                    weight=QC_WEIGHTS["age_appropriateness"], note=safety_note)
        )
        if not safety_ok:
            issues.append(QcIssue(severity="critical", area="policy",
                                  message=f"Safety review failed: {safety_note}",
                                  regenerate=["script"]))

        # 8. copyright safety — known IP markers
        ip_markers = ("peppa", "paw patrol", "elsa", "frozen", "mickey", "pokemon", "bluey", "cocomelon",
                      "baby shark", "disney", "marvel")
        ip_hits = [m for m in ip_markers if m in lowered]
        checks.append(
            QcCheck(id="copyright_safety", label="Originality / IP", passed=not ip_hits,
                    weight=QC_WEIGHTS["copyright_safety"],
                    note="no known IP" if not ip_hits else f"IP markers: {', '.join(ip_hits)}")
        )
        if ip_hits:
            issues.append(QcIssue(severity="critical", area="copyright",
                                  message=f"Known IP references: {', '.join(ip_hits)}", regenerate=["script"]))
            regenerate.add("script")

        score = round(sum(c.weight for c in checks if c.passed) / sum(c.weight for c in checks) * 100, 1)
        per_scene_incomplete = bool(missing_images or missing_audio)
        if any(i.severity == "critical" for i in issues) or per_scene_incomplete:
            status = "fail"
        elif score < payload.min_score:
            status = "review" if score >= payload.min_score - 10 else "fail"
        elif any(c.id == "script_quality" for c in checks if not c.passed):
            status = "review"
        else:
            status = "pass"

        recommendations: list[str] = []
        if not render_ok:
            recommendations.append("Re-run the render step before requesting approval.")
        if missing_audio:
            recommendations.append("Regenerate narration for the scenes listed above.")
        if status == "review":
            recommendations.append("Review flagged items manually before approval.")
        if not issues and status == "pass":
            recommendations.append("Ready for approval. Consider A/B testing the thumbnail text.")

        return AgentResult(
            output=QualityReport(
                score=score,
                approval_status=status,
                checks=checks,
                issues=issues,
                warnings=warnings,
                recommendations=recommendations,
                regenerate=sorted(regenerate),
            ),
            usage=usage,
            provider=usage.provider,
            model="qc",
        )


# --------------------------------------------------------------------------- publishing


class PublishRequest(Contract):
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    privacy: str = "private"
    made_for_kids: bool = True
    scheduled_for: str | None = None  # ISO 8601 UTC
    video_key: str
    thumbnail_key: str | None = None


class PublishResult(BaseModel):
    youtube_video_id: str
    url: str
    privacy: str
    made_for_kids: bool


class PublishingAgent:
    key = "publishing"
    name = "Publishing"
    InputModel = PublishRequest
    OutputModel = PublishResult

    async def run(self, ctx: AgentContext, payload: PublishRequest) -> AgentResult[PublishResult]:
        if ctx.youtube is None:
            raise AgentError("YouTube provider is not configured", agent_key=self.key, retryable=False)
        access_token = ctx.params.get("access_token")
        if not access_token:
            raise AgentError("YouTube channel is not connected (OAuth token missing)",
                             agent_key=self.key, retryable=False)
        storage = ctx.require_storage()
        video_bytes = await storage.get_bytes(payload.video_key)
        thumbnail_bytes = await storage.get_bytes(payload.thumbnail_key) if payload.thumbnail_key else None
        from datetime import datetime

        scheduled = datetime.fromisoformat(payload.scheduled_for) if payload.scheduled_for else None
        result = await ctx.youtube.upload(
            access_token,
            UploadRequest(
                title=payload.title,
                description=payload.description,
                tags=payload.tags,
                privacy=payload.privacy,
                made_for_kids=payload.made_for_kids,
                scheduled_for=scheduled,
                video_bytes=video_bytes,
                thumbnail_bytes=thumbnail_bytes,
            ),
        )
        return AgentResult(
            output=PublishResult(
                youtube_video_id=result.youtube_video_id,
                url=result.url,
                privacy=payload.privacy,
                made_for_kids=payload.made_for_kids,
            ),
            usage=Usage(provider="youtube", model="v3", operation="upload", units=1, unit_label="upload"),
            provider="youtube",
            model="v3",
            artifacts={"youtube_video_id": result.youtube_video_id},
        )


# --------------------------------------------------------------------------- analytics


class AnalyticsInput(Contract):
    channel_name: str
    videos: list[dict[str, Any]] = Field(default_factory=list)
    period_days: int = 28


class AnalyticsResult(BaseModel):
    top_performers: list[dict[str, Any]]
    insights: list[str]
    recommendations: list[str]
    avg_ctr: float | None = None
    avg_view_duration_s: float | None = None


class AnalyticsAgent:
    """Computes performance leaderboard deterministically; optional LLM insights are not required."""

    key = "analytics"
    name = "Analytics"
    InputModel = AnalyticsInput
    OutputModel = AnalyticsResult

    async def run(self, ctx: AgentContext, payload: AnalyticsInput) -> AgentResult[AnalyticsResult]:
        scored = sorted(
            payload.videos,
            key=lambda v: (v.get("views", 0) or 0) * max(1.0, v.get("avg_view_duration_s", 0) or 0),
            reverse=True,
        )
        top = scored[:5]
        insights: list[str] = []
        recs: list[str] = []
        if scored:
            best = top[0]
            insights.append(
                f"Top video “{best.get('title', 'n/a')}” holds {best.get('views', 0):,} views "
                f"with {best.get('avg_view_duration_s') or 0:.0f}s average view duration."
            )
            recs.append("Plan the next production around the topic pattern of the top performer.")
        if not any(v.get("impressions") for v in payload.videos):
            insights.append("Impressions and CTR are unavailable until Analytics scope is granted.")
        return AgentResult(
            output=AnalyticsResult(
                top_performers=top,
                insights=insights,
                recommendations=recs,
                avg_ctr=_mean([v.get("ctr") for v in payload.videos if v.get("ctr") is not None]),
                avg_view_duration_s=_mean(
                    [v.get("avg_view_duration_s") for v in payload.videos
                     if v.get("avg_view_duration_s") is not None]
                ),
            ),
            usage=Usage(provider="rules", model="analytics", operation="rules", units=1, unit_label="run"),
            provider="rules",
            model="analytics",
        )


# --------------------------------------------------------------------------- helpers


def _avg_sentence_length(text: str) -> float:
    import re

    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if not sentences:
        return 0.0
    return sum(len(s.split()) for s in sentences) / len(sentences)


def _mean(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def _merge(a: Usage, b: Usage) -> Usage:
    return Usage(
        provider=b.provider or a.provider,
        model=b.model or a.model,
        operation="rules",
        input_tokens=a.input_tokens + b.input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        units=a.units + b.units,
        unit_label="check",
        cost_usd=a.cost_usd + b.cost_usd,
        latency_ms=max(a.latency_ms, b.latency_ms),
    )
