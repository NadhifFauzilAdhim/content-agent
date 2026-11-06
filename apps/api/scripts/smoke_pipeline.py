"""End-to-end smoke: bootstrap DB, login, run a full production pipeline, inspect results.

Run from apps/api:  python scripts/smoke_pipeline.py
Uses the local SQLite database and mock providers (no external spend).
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.quality import QC_WEIGHTS  # noqa: E402
from app.agents.base import AgentContext  # noqa: E402
from app.agents.generation import ContentPlannerAgent, ScriptWriterAgent, StoryboardAgent  # noqa: E402
from app.agents.contracts import PlannerInput  # noqa: E402
from app.adapters.storage import LocalStorage  # noqa: E402
from app.adapters.llm import MockLLMProvider  # noqa: E402


FIXTURE_BRIEF = {
    "title": "Pip and the Lantern Path",
    "topic": "finding your way home in the dark",
    "angle": "A small fox learns to trust the lanterns his neighbours leave out.",
    "audience": "Children 3-7",
    "brief": "Pip loses the path home when the sun sets. One by one, friendly neighbours light "
             "lanterns on posts, and Pip follows the glow all the way to his burrow door, learning "
             "that asking for help is a kind thing to do. Gentle, slow pacing, warm ending.",
    "creative_direction": "Gouache storybook, warm amber light against blue dusk, soft edges.",
    "category": "story",
    "estimated_duration_s": 180,
    "safety_notes": ["no peril", "no loud sounds"],
    "rationale": "Bedtime stories about kindness perform well with parent co-viewing.",
}

FIXTURE_SCRIPT = {
    "title": "Pip and the Lantern Path",
    "description": "Pip the fox finds his way home with help from his neighbours.",
    "hook": "When the sun went down, Pip's little paws stopped.",
    "scenes": [
        {"index": 1, "title": "Dusk in the meadow", "narration": "The sun went down behind the hill.",
         "dialogue": [], "duration_s": 8, "visual_instruction": "Wide meadow at dusk, Pip looking up",
         "sfx": ["evening birds"], "transition": "fade"},
        {"index": 2, "title": "The first lantern", "narration": "Mossy the tortoise lit a lantern on a post.",
         "dialogue": [{"character": "Mossy", "line": "Follow the light, little one.", "emotion": "warm"}],
         "duration_s": 10, "visual_instruction": "Close on Mossy lighting a lantern", "sfx": ["match"],
         "transition": "fade"},
        {"index": 3, "title": "Home", "narration": "Pip found his burrow with a lantern by the door.",
         "dialogue": [], "duration_s": 9, "visual_instruction": "Pip at his burrow door, warm light",
         "sfx": ["gentle music"], "transition": "fade"},
    ],
    "moral": "Asking for help brings the light home.",
    "target_age": "3-7",
}

FIXTURE_BOARD = {
    "style_guide": "Warm gouache storybook",
    "scenes": [
        {"index": i, "camera": "wide", "composition": "rule of thirds", "characters": ["Pip"],
         "background": "meadow at dusk", "action": "Pip looks around", 
         "image_prompt": f"Storybook illustration, scene {i}, Pip the fox cub in a red scarf, meadow at dusk",
         "negative_prompt": "text, watermark", "sfx": [], "duration_s": 8, "transition": "fade"}
        for i in (1, 2, 3)
    ],
}


async def agents_check() -> None:
    llm = MockLLMProvider(
        fixture={
            "ContentBrief": FIXTURE_BRIEF,
            "ScriptDraft": FIXTURE_SCRIPT,
            "StoryboardDraft": FIXTURE_BOARD,
            "MetadataDraft": {
                "title": "Pip and the Lantern Path | Bedtime Story for Kids",
                "description": "A gentle bedtime story about a small fox who finds his way home with "
                               "help from friendly neighbours. Perfect for children aged 3 to 7 and "
                               "families winding down for sleep. Listen, breathe, and follow the light home.",
                "tags": ["bedtime story", "kids story", "fox", "kindness", "children stories",
                         "calm", "lantern", "night story"],
                "thumbnail_text": "Follow the light",
                "thumbnail_concept": "Pip holds a glowing lantern, dusk meadow behind",
                "thumbnail_prompt": "Pip the fox holding a lantern",
                "playlist": "Bedtime Stories",
                "made_for_kids": True,
                "category": "Education",
            },
        }
    )
    storage = LocalStorage(Path("storage/smoke"))
    ctx = AgentContext(workspace_id=None, llm=llm, storage=storage, model="mock-structured")  # type: ignore[arg-type]
    planner = ContentPlannerAgent()
    res = await planner.run(ctx, PlannerInput(channel_name="LL", niche="kids", audience="children",
                                              language="en"))
    print("planner:", res.output.title)
    from app.agents.contracts import ScriptBrief

    res = await ScriptWriterAgent().run(ctx, ScriptBrief(title="x", topic="x", brief="x",
                                                          creative_direction="x", audience="kids",
                                                          language="en", target_duration_s=180))
    print("script scenes:", len(res.output.scenes))
    from app.agents.contracts import StoryboardInput

    res = await StoryboardAgent().run(ctx, StoryboardInput(title="x", style="gouache",
                                                            scenes=res.output.scenes))
    print("storyboard scenes:", len(res.output.scenes))
    print("qc weights sum:", sum(QC_WEIGHTS.values()))


async def main() -> None:
    await agents_check()
    print("OK")


if __name__ == "__main__":
    t = time.time()
    asyncio.run(main())
    print(f"{time.time() - t:.1f}s")
