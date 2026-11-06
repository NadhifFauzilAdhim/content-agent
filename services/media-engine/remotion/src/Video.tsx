/**
 * The render engine.
 *
 * One composition drives every template. It owns:
 *   intro card → scenes (with overlapping transitions) → outro card
 *   narration and sound effects per scene
 *   background music with fades and ducking under narration
 *   captions (rendered as React, not a subtitle file)
 *
 * Templates only supply the look of a scene, the title card and the outro. That separation is why
 * a new template never touches the renderer, the timeline or the audio graph.
 */

import type React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import {getTemplate} from "./catalogue";
import {buildTimeline} from "./timeline";
import type {StoryboardProps, VideoSpec} from "./types";

export const StoryboardVideo: React.FC<StoryboardProps> = ({spec}) => {
  const template = getTemplate(spec.templateId);
  const timeline = buildTimeline(spec);
  const {fps} = useVideoConfig();
  const Scene = template.Scene;

  return (
    <AbsoluteFill style={{backgroundColor: spec.background}}>
      {spec.intro?.enabled ? (
        <Sequence
          from={0}
          durationInFrames={timeline.introFrames}
          name="intro"
          style={{backgroundColor: spec.background}}
        >
          <template.Title
            spec={spec}
            headline={spec.intro.title}
            subline={spec.intro.subtitle}
            frames={timeline.introFrames}
          />
        </Sequence>
      ) : null}

      {timeline.scenes.map((placed) => {
        const transition =
          placed.scene.animation?.transitionIn ?? placed.scene.transition ?? spec.defaultTransition;
        return (
          <Sequence
            key={placed.scene.id}
            from={placed.from}
            durationInFrames={placed.durationInFrames}
            name={`scene ${String(placed.scene.index).padStart(2, "0")}`}
          >
            <TransitionedScene kind={transition} overlapFrames={placed.overlapIn}>
              <Scene spec={spec} scene={placed.scene} frames={placed.durationInFrames} />
            </TransitionedScene>
          </Sequence>
        );
      })}

      {spec.outro?.enabled ? (
        <Sequence
          from={timeline.totalFrames - timeline.outroFrames}
          durationInFrames={timeline.outroFrames}
          name="outro"
        >
          <template.Outro
            spec={spec}
            headline={spec.outro.headline}
            subline={spec.outro.subline}
            cta={spec.outro.cta}
            frames={timeline.outroFrames}
          />
        </Sequence>
      ) : null}

      <Narration spec={spec} />
      <SoundEffects spec={spec} />
      <MusicBed spec={spec} totalFrames={timeline.totalFrames} fps={fps} />
    </AbsoluteFill>
  );
};

/**
 * Each scene animates in over the previous one for `overlapFrames`; the first scene and `cut`
 * transitions start fully visible.
 */
const TransitionedScene: React.FC<{
  kind: string;
  overlapFrames: number;
  children: React.ReactNode;
}> = ({kind, overlapFrames, children}) => {
  const frame = useCurrentFrame();
  const style = transitionStyle(kind, frame, overlapFrames);
  return <AbsoluteFill style={style}>{children}</AbsoluteFill>;
};

function transitionStyle(kind: string, frame: number, overlap: number): React.CSSProperties {
  if (overlap <= 0 || kind === "cut") return {};
  const p = interpolate(frame, [0, overlap], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  switch (kind) {
    case "slide-left":
      return {transform: `translateX(${(1 - p) * 100}%)`};
    case "slide-up":
      return {transform: `translateY(${(1 - p) * 100}%)`};
    case "zoom":
      return {opacity: p, transform: `scale(${1.08 - p * 0.08})`};
    case "iris":
      return {clipPath: `circle(${p * 78}% at 50% 50%)`};
    case "wipe":
      return {clipPath: `inset(0 ${(1 - p) * 100}% 0 0)`};
    default:
      return {opacity: p};
  }
}

/**
 * Narration is attached at the composition level (not inside the scene frame) so a transition
 * never fades the voice: the picture crossfades, speech stays continuous.
 */
const Narration: React.FC<{spec: VideoSpec}> = ({spec}) => {
  const timeline = buildTimeline(spec);
  return (
    <>
      {timeline.scenes.map(({scene, from}) =>
        scene.narrationSrc ? (
          <Sequence key={`nar-${scene.id}`} from={from} layout="none" name={`narration ${scene.index}`}>
            <Audio src={staticFile(scene.narrationSrc)} volume={1} />
          </Sequence>
        ) : null,
      )}
    </>
  );
};

const SoundEffects: React.FC<{spec: VideoSpec}> = ({spec}) => {
  const timeline = buildTimeline(spec);
  return (
    <>
      {timeline.scenes.flatMap(({scene, from}) =>
        (scene.sfx ?? []).map((sfx, i) => (
          <Sequence
            key={`sfx-${scene.id}-${i}`}
            from={from + Math.max(0, Math.round((sfx.atS ?? 0) * spec.fps))}
            layout="none"
            name={`sfx ${scene.index}.${i}`}
          >
            <Audio src={staticFile(sfx.src)} volume={sfx.volume ?? 0.6} />
          </Sequence>
        )),
      )}
    </>
  );
};

/**
 * Background music: loops for the whole composition, fades in/out and ducks under narration.
 * Ducking is computed from the timeline (narration start/end per scene) rather than analysing
 * audio, so it is deterministic and identical in preview and render.
 */
const MusicBed: React.FC<{spec: VideoSpec; totalFrames: number; fps: number}> = ({
  spec,
  totalFrames,
  fps,
}) => {
  const frame = useCurrentFrame();
  const music = spec.music;
  if (music?.url == null) return null;

  const timeline = buildTimeline(spec);
  const narrationOn = timeline.scenes.some(({scene, from}) => {
    if (!scene.narrationSrc) return false;
    const end = from + Math.round(scene.durationS * fps);
    return frame >= from - 2 && frame <= end;
  });
  const base = music.volume;
  const ducked = music.duckUnderNarration && narrationOn ? base * 0.35 : base;
  const fadeIn = interpolate(frame, [0, Math.round((music.fadeInS ?? 1) * fps)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    frame,
    [totalFrames - Math.round((music.fadeOutS ?? 2) * fps), totalFrames],
    [1, 0],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
  );
  const volume = Math.max(0, Math.min(1, ducked * fadeIn * fadeOut));

  return <Audio src={staticFile(music.url)} volume={volume} loop />;
};
