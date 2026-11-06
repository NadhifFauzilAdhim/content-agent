/**
 * Captions and small overlays.
 *
 * Subtitles are React components (not a burned-in subtitle file): they scale with the composition,
 * can highlight words, animate, and are composited by Remotion's own encoder. Cue timing is
 * weighted by character count and clamped to the scene, so subtitles stay in step with narration
 * even when the measured TTS duration differs from the storyboard estimate.
 */

import React from "react";
import {interpolate} from "remotion";

import {MONO, SERIF, entrance} from "./motion";
import {cueWeights, splitCues} from "./timeline";
import type {CaptionStyle, StoryboardScene} from "./types";

const INK = "#111111";

export function Captions({
  scene,
  style,
  localFrame,
  frames,
  accent,
}: {
  scene: StoryboardScene;
  style: Exclude<CaptionStyle, "none">;
  localFrame: number;
  frames: number;
  accent: string;
}) {
  const text = (scene.caption ?? "").trim();
  if (!text) return null;

  const cues = splitCues(text, style === "subtitle" ? 78 : 110);
  const weights = cueWeights(cues);
  const fps = sceneFps(scene, frames);
  const showStart = Math.min(Math.round(fps * 0.3), Math.floor(frames * 0.12));
  const showEnd = Math.max(showStart + 4, frames - Math.round(fps * 0.15));

  let cursor = showStart;
  const spans = cues.map((cue, i) => {
    const length = Math.max(1, Math.round((showEnd - showStart) * weights[i]));
    const span = {cue, from: cursor, to: cursor + length};
    cursor += length;
    return span;
  });
  const active =
    spans.find((s) => localFrame >= s.from && localFrame < s.to) ?? spans[spans.length - 1];
  if (!active) return null;

  const localP = interpolate(localFrame, [active.from, active.to], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeIn = interpolate(localFrame, [active.from, active.from + 6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (style === "overlay-title") {
    return (
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "center",
          padding: "0 11% 20%",
          opacity: fadeIn,
        }}
      >
        <div
          style={{
            fontFamily: SERIF,
            fontSize: "3.6cqw",
            lineHeight: 1.25,
            color: "#FFFFFF",
            textAlign: "center",
            textShadow: "0 4px 30px rgba(0,0,0,0.75), 0 1px 4px rgba(0,0,0,0.6)",
            transform: `translateY(${(1 - localP) * 10}px)`,
          }}
        >
          {active.cue}
        </div>
      </div>
    );
  }

  if (style === "subtitle") {
    return (
      <div
        style={{
          position: "absolute",
          left: "50%",
          bottom: "9%",
          transform: `translateX(-50%) translateY(${(1 - fadeIn) * 8}px)`,
          opacity: fadeIn,
          width: "84%",
        }}
      >
        <div
          style={{
            backgroundColor: "rgba(17,17,17,0.84)",
            color: "#FFFFFF",
            fontFamily: 'Geist, "Helvetica Neue", Arial, sans-serif',
            fontWeight: 600,
            fontSize: "2.5cqw",
            lineHeight: 1.25,
            padding: "0.42em 0.7em",
            textAlign: "center",
            letterSpacing: "-0.005em",
          }}
        >
          <Words cue={active.cue} localP={localP} highlight={accent} />
        </div>
      </div>
    );
  }

  // lower third — the editorial default: opaque paper band so captions stay readable on any art
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        padding: "2.2% 5% 3.4%",
        backgroundColor: "rgba(255,255,255,0.97)",
        borderTop: `2px solid ${INK}`,
        opacity: fadeIn,
      }}
    >
      <div style={{display: "flex", alignItems: "flex-start", gap: "1.2cqw"}}>
        <div style={{width: 10, height: 10, backgroundColor: accent, marginTop: "1cqw", flexShrink: 0}} />
        <div
          style={{
            fontFamily: SERIF,
            fontSize: "2.95cqw",
            lineHeight: 1.16,
            color: INK,
            maxWidth: "82%",
            transform: entrance("rise", localP).transform,
          }}
        >
          {active.cue}
        </div>
      </div>
    </div>
  );
}

function sceneFps(scene: StoryboardScene, frames: number): number {
  const duration = Math.max(0.5, scene.durationS);
  return Math.max(1, frames / duration);
}

/** Progressive word reveal when the API supplied no per-word timings. */
function Words({cue, localP, highlight}: {cue: string; localP: number; highlight: string}) {
  const words = cue.split(/\s+/).filter(Boolean);
  const idx = Math.min(words.length - 1, Math.floor(localP * words.length));
  return (
    <>
      {words.map((word, i) => (
        <span
          key={`${word}-${i}`}
          style={{opacity: i <= idx ? 1 : 0.58, color: i === idx ? "#FFFFFF" : undefined}}
        >
          {word}
          {i < words.length - 1 ? " " : ""}
        </span>
      ))}
      <span aria-hidden style={{display: "none"}}>{highlight}</span>
    </>
  );
}

export function ProgressBar({
  progress,
  accent,
  position = "bottom",
}: {
  progress: number;
  accent: string;
  position?: "top" | "bottom";
}) {
  const style: React.CSSProperties = {
    position: "absolute",
    left: 0,
    right: 0,
    height: 6,
    backgroundColor: "rgba(17,17,17,0.14)",
  };
  if (position === "top") style.top = 0;
  else style.bottom = 0;
  return (
    <div style={style}>
      <div style={{height: 6, width: `${Math.min(100, progress * 100)}%`, backgroundColor: accent}} />
    </div>
  );
}

export function BrandMark({
  brand,
  accent,
  tone = "ink",
}: {
  brand: string;
  accent: string;
  tone?: "ink" | "light";
}) {
  return (
    <div
      style={{
        position: "absolute",
        right: "3.6%",
        bottom: "3.4%",
        display: "flex",
        alignItems: "center",
        gap: 8,
        opacity: 0.9,
      }}
    >
      <span style={{width: 8, height: 8, backgroundColor: accent}} />
      <span
        style={{
          fontFamily: MONO,
          fontSize: "1.05cqw",
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: tone === "ink" ? INK : "#FFFFFF",
        }}
      >
        {brand}
      </span>
    </div>
  );
}
