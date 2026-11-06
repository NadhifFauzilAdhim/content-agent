/**
 * Timeline maths shared by the composition, the player and the API's QC.
 *
 * Scenes are chained with *overlapping* transitions: scene N+1 starts `transitionFrames` before
 * scene N ends. That is how crossfades, slides and wipes are composed without separate clips, and
 * it keeps narration continuous (each scene's audio starts at its own scene start).
 */

import type {StoryboardScene, VideoSpec} from "./types";

export type PlacedScene = {
  scene: StoryboardScene;
  /** Inclusive start frame within the composition. */
  from: number;
  durationInFrames: number;
  /** Frames the incoming transition overlaps the previous scene (0 for the first scene). */
  overlapIn: number;
};

export type Timeline = {
  scenes: PlacedScene[];
  introFrames: number;
  outroFrames: number;
  totalFrames: number;
  /** Absolute frame where scene index 0 starts (after the intro). */
  bodyStart: number;
};

export const MIN_SCENE_FRAMES = 12;

export function sceneFrames(scene: StoryboardScene, fps: number, speed = 1): number {
  const authored = Math.max(scene.durationS, 0.5) / Math.max(speed, 0.1);
  return Math.max(MIN_SCENE_FRAMES, Math.round(authored * fps));
}

export function buildTimeline(spec: Pick<
  VideoSpec,
  "scenes" | "fps" | "intro" | "outro" | "defaultTransition" | "transitionDurationS" | "speed"
>): Timeline {
  const fps = spec.fps;
  const transitionFrames = Math.max(0, Math.round(spec.transitionDurationS * fps));
  const introFrames = spec.intro?.enabled ? Math.max(1, Math.round(spec.intro.durationS * fps)) : 0;
  const outroFrames = spec.outro?.enabled ? Math.max(1, Math.round(spec.outro.durationS * fps)) : 0;

  const scenes: PlacedScene[] = [];
  let cursor = introFrames;
  spec.scenes.forEach((scene, i) => {
    const durationInFrames = sceneFrames(scene, fps, spec.speed);
    const transition = scene.animation?.transitionIn ?? scene.transition ?? spec.defaultTransition;
    const requested = scene.animation?.transitionDurationInFrames ??
      Math.round(spec.transitionDurationS * fps);
    // A transition can never eat more than a third of either neighbour.
    const overlapIn = i === 0 || transition === "cut"
      ? 0
      : Math.max(0, Math.min(transitionFrames, requested, Math.floor(durationInFrames / 3)));
    const from = i === 0 ? cursor : cursor - overlapIn;
    scenes.push({scene, from, durationInFrames, overlapIn});
    cursor = from + durationInFrames;
  });

  const totalFrames = Math.max(MIN_SCENE_FRAMES, cursor + outroFrames);
  return {scenes, introFrames, outroFrames, totalFrames, bodyStart: introFrames};
}

/** Seconds where each scene starts — used for subtitles, QC and the editor timeline. */
export function sceneStartSeconds(timeline: Timeline, fps: number): number[] {
  return timeline.scenes.map((s) => s.from / fps);
}

/**
 * Split a caption into short, readable subtitle cues. Splits on sentence punctuation first so a
 * cue never cuts a sentence mid-clause unless the sentence itself is too long.
 */
export function splitCues(text: string, maxChars = 90): string[] {
  const normalised = text.replace(/\s+/g, " ").trim();
  if (!normalised) return [];
  if (normalised.length <= maxChars) return [normalised];
  const sentences = normalised.match(/[^.!?…]+[.!?…]*/g) ?? [normalised];
  const cues: string[] = [];
  let current = "";
  for (const sentence of sentences) {
    const s = sentence.trim();
    if (!s) continue;
    if (!current) {
      current = s;
    } else if (`${current} ${s}`.length <= maxChars) {
      current = `${current} ${s}`;
    } else {
      cues.push(current);
      current = s;
    }
    while (current.length > maxChars) {
      const cut = current.lastIndexOf(" ", maxChars);
      const at = cut > maxChars * 0.4 ? cut : maxChars;
      cues.push(current.slice(0, at).trim());
      current = current.slice(at).trim();
    }
  }
  if (current) cues.push(current);
  return cues;
}

/**
 * Weight cue durations by character count (speech length is roughly proportional to characters),
 * so subtitles stay in step with narration instead of each cue taking an equal slice.
 */
export function cueWeights(cues: string[]): number[] {
  const weights = cues.map((c) => Math.max(8, c.replace(/\s+/g, "").length));
  const total = weights.reduce((a, b) => a + b, 0) || 1;
  return weights.map((w) => w / total);
}
