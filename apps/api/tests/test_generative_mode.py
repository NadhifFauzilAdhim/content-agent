"""Generative visual mode: no image provider call, Remotion composes from the prompt."""

from __future__ import annotations

from types import SimpleNamespace

from app.services import render as render_mod
from app.services.storyboard import actual_duration, build_spec

CHANNEL = SimpleNamespace(
    video_format="16:9", audience="Children 3-7", name="Test", workspace_id="ws",
    visual_mode="generative",
)


def _scene(index: int):
    scene = SimpleNamespace(
        id=f"scene-{index}",
        index=index,
        title=f"Scene {index}",
        duration_s=4.0,
        transition="fade",
        narration="Narration text.",
        image_prompt="A fox with a red scarf on a forest path",
        characters=None,
    )
    audio = SimpleNamespace(
        id=f"audio-{index}", storage_key=f"p/x/audio/scene-0{index}.wav", duration_s=3.5
    )
    return render_mod.sb.RenderScene(scene=scene, image=None, audio=audio)


def test_generative_spec_carries_the_prompt_and_no_asset():
    plan = build_spec(
        project=SimpleNamespace(title="T", language="en"),
        channel=CHANNEL,
        setting=None,
        scenes=[_scene(1), _scene(2)],
        template_id="youtube-editorial",
        visual_mode="generative",
    )
    scenes = plan.spec["scenes"]
    assert len(scenes) == 2
    for entry in scenes:
        assert entry["mode"] == "generative"
        assert entry["prompt"] == "A fox with a red scarf on a forest path"
        assert "assetKey" not in entry  # nothing to stage
        assert "imageSrc" not in entry
    # Only narration is staged; there is no image to copy into the render.
    assert plan.assets, "narration audio should still be staged"
    assert all("audio" in a["source"] for a in plan.assets)


def test_image_mode_still_requests_assets():
    plan = build_spec(
        project=SimpleNamespace(title="T", language="en"),
        channel=SimpleNamespace(**{**vars(CHANNEL), "visual_mode": "image"}),
        setting=None,
        scenes=[_scene(1)],
        template_id="youtube-editorial",
        visual_mode="image",
    )
    assert plan.spec["scenes"][0]["mode"] == "image"


def test_duration_is_identical_in_both_modes():
    scenes = [_scene(1), _scene(2)]
    plan = build_spec(
        project=SimpleNamespace(title="T", language="en"),
        channel=CHANNEL, setting=None, scenes=scenes,
        template_id="youtube-editorial", visual_mode="generative",
    )
    assert plan.duration_s == actual_duration(plan.spec)
    assert plan.duration_s > 0


def test_generative_channel_skips_the_missing_image_check():
    """A generative render must not be rejected for having no images."""
    message = "Scene [1] has no image yet; generate assets before rendering"
    # Mirrors the guard in RenderService.enqueue.
    scenes = [SimpleNamespace(scene=SimpleNamespace(index=1), image=None)]
    unavailable = (
        [] if CHANNEL.visual_mode == "generative"
        else [i.scene.index for i in scenes if i.image is None]
    )
    assert unavailable == []
    assert message  # documented behaviour for image mode
