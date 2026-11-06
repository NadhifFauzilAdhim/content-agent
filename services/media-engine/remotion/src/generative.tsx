/**
 * Generative scenes — no image asset at all.
 *
 * When a channel runs in ``generative`` mode the storyboard agent still writes a visual prompt per
 * scene, but nothing is sent to an image provider. Instead the prompt is the *input* to this
 * component: it is hashed into a deterministic palette, composition and motion set, so the same
 * prompt always produces the same frames (renders stay reproducible) while different scenes look
 * genuinely different.
 *
 * The result is a designed scene, not a placeholder: layered colour fields, a slow drifting key
 * shape, grain, rule lines drawn in the editorial language, and the prompt's keywords treated as
 * typographic material.
 *
 * Everything is derived from `useCurrentFrame()` — no randomness, no timers.
 */

import type React from "react";
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from "remotion";

import {MONO, SERIF} from "./motion";

/** Small, fast string hash (FNV-1a) so a prompt maps to stable numbers across renders. */
export function hashPrompt(text: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

type Palette = {
  sky: [string, string];
  land: string;
  accent: string;
  ink: string;
};

const PALETTES: Palette[] = [
  {sky: ["#1F2A44", "#3E5677"], land: "#0E1626", accent: "#E8C36A", ink: "#F5F1E8"},
  {sky: ["#F6EBDD", "#E5C9AD"], land: "#B57C5B", accent: "#7A3E2F", ink: "#2B2118"},
  {sky: ["#12312B", "#2E6B5A"], land: "#0A1F1B", accent: "#D6FF45", ink: "#EAF6E8"},
  {sky: ["#2C1B3D", "#5A3A72"], land: "#170E22", accent: "#F2A65A", ink: "#F7EEF7"},
  {sky: ["#0B1B2A", "#1E4159"], land: "#071019", accent: "#7FD1FF", ink: "#EAF2FA"},
  {sky: ["#FFF6EC", "#FFE0C2"], land: "#E8B94B", accent: "#C4553B", ink: "#33251C"},
];

const round = (n: number) => Math.round(n);

/** Deterministic 0..1 from a hashed value and a channel index. */
function unit(hash: number, channel: number): number {
  const mixed = Math.imul(hash ^ (channel * 0x9e3779b9), 0x85ebca6b) >>> 0;
  return (mixed % 1000) / 1000;
}

/** Colour fields that drift: the slowest, widest layer of motion. */
const Sky: React.FC<{palette: Palette; frame: number; frames: number; hash: number}> = ({
  palette,
  frame,
  frames,
  hash,
}) => {
  const drift = interpolate(frame, [0, Math.max(1, frames)], [0, 1], {
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.sin),
  });
  const tilt = (unit(hash, 1) - 0.5) * 24;
  const bandTop = 30 + unit(hash, 2) * 22;
  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(${160 + tilt}deg, ${palette.sky[0]} 0%, ${palette.sky[1]} 100%)`,
      }}
    >
      {/* land / ground mass, rising slowly */}
      <div
        style={{
          position: "absolute",
          left: "-10%",
          right: "-10%",
          top: `${bandTop + 18 - drift * 3}%`,
          bottom: "-10%",
          backgroundColor: palette.land,
          borderTopLeftRadius: "48% 70%",
          borderTopRightRadius: "60% 52%",
        }}
      />
      {/* horizon glow behind the subject */}
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: `${bandTop + 4}%`,
          width: "46%",
          aspectRatio: "1 / 1",
          transform: `translate(-50%, -50%) scale(${1 + drift * 0.06})`,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${palette.accent}55 0%, transparent 70%)`,
        }}
      />
    </AbsoluteFill>
  );
};

/** The "subject": layered silhouette shapes standing in for the prompt's focal object. */
const Subject: React.FC<{palette: Palette; frame: number; frames: number; hash: number}> = ({
  palette,
  frame,
  frames,
  hash,
}) => {
  const sway = Math.sin(frame / 34) * 5;
  const rise = interpolate(frame, [0, Math.min(frames, 40)], [30, 0], {
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const breathe = 1 + Math.sin(frame / 48) * 0.012;
  const variant = unit(hash, 3);
  const left = 18 + unit(hash, 4) * 26;
  const base = 52 + unit(hash, 5) * 8; // ground line in %
  const scale = 0.85 + unit(hash, 6) * 0.35;
  const transform = `translateY(${rise}px) translateX(${sway}px) scale(${breathe * scale})`;

  // Three silhouettes: a tall shape (tree/character), a soft mass (hill/bush), a small companion.
  const tallW = 7 + unit(hash, 7) * 6;
  const tallH = 20 + unit(hash, 8) * 16;
  const companion = unit(hash, 9) > 0.4;

  return (
    <AbsoluteFill style={{opacity: 0.95}}>
      {variant > 0.55 && (
        <div
          style={{
            position: "absolute",
            left: "8%",
            top: `${base - 16}%`,
            width: "26%",
            height: "18%",
            transform,
            borderRadius: "60% 70% 38% 42% / 80% 74% 26% 20%",
            backgroundColor: palette.land,
            filter: "brightness(0.8)",
          }}
        />
      )}
      <div
        style={{
          position: "absolute",
          left: `${left}%`,
          top: `${base - tallH}%`,
          width: `${tallW}%`,
          height: `${tallH}%`,
          transform,
          borderRadius: `${30 + unit(hash, 11) * 30}% ${40 + unit(hash, 12) * 30}% ${
            18 + unit(hash, 13) * 20
          }% ${22 + unit(hash, 14) * 20}% / 24% 30% 10% 12%`,
          backgroundColor: palette.ink,
          boxShadow: "0 30px 80px rgba(0,0,0,0.35)",
        }}
      />
      {companion && (
        <div
          style={{
            position: "absolute",
            left: `${left + tallW + 3}%`,
            top: `${base - tallH * 0.34}%`,
            width: `${tallW * 0.5}%`,
            height: `${tallH * 0.34}%`,
            transform,
            borderRadius: "50% 50% 44% 46% / 46% 48% 52% 50%",
            backgroundColor: palette.accent,
            opacity: 0.92,
          }}
        />
      )}
    </AbsoluteFill>
  );
};

/** Drifting motes: a few dozen dots with independent parallax. */
const Motes: React.FC<{palette: Palette; frame: number; frames: number; hash: number}> = ({
  palette,
  frame,
  frames,
  hash,
}) => {
  const count = 34;
  const progress = frame / Math.max(1, frames);
  return (
    <AbsoluteFill>
      {Array.from({length: count}).map((_, i) => {
        const x = unit(hash, 10 + i) * 100;
        const startY = unit(hash, 60 + i) * 110 - 10;
        const speed = 0.4 + unit(hash, 120 + i) * 1.2;
        const y = startY - progress * speed * 22;
        const size = 2 + unit(hash, 180 + i) * 5;
        const opacity = 0.15 + unit(hash, 240 + i) * 0.4;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: `${x}%`,
              top: `${y % 110}%`,
              width: size,
              height: size,
              borderRadius: "50%",
              backgroundColor: palette.accent,
              opacity,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/** Editorial rules that draw themselves in, and the prompt's keywords set as type. */
const TypographicLayer: React.FC<{
  palette: Palette;
  frame: number;
  frames: number;
  hash: number;
  keywords: string[];
  title?: string;
}> = ({palette, frame, frames, hash, keywords, title}) => {
  const draw = interpolate(frame, [6, 26], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.quad),
  });
  const fade = interpolate(frame, [18, 40], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
  const alignRight = unit(hash, 7) > 0.5;
  const words = (title ? [title] : keywords).slice(0, 3);

  return (
    <AbsoluteFill style={{pointerEvents: "none"}}>
      <div
        style={{
          position: "absolute",
          left: "6%",
          right: "6%",
          top: "7%",
          height: 2,
          backgroundColor: palette.ink,
          opacity: 0.45,
          transform: `scaleX(${draw})`,
          transformOrigin: alignRight ? "right center" : "left center",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: "30%",
          [alignRight ? "left" : "right"]: "6%",
          maxWidth: "40%",
          textAlign: alignRight ? "left" : "right",
          opacity: fade,
        }}
      >
        {words.map((word, i) => (
          <div
            key={`${word}-${i}`}
            style={{
              fontFamily: i === 0 ? SERIF : MONO,
              fontStyle: i === 0 ? "italic" : "normal",
              fontSize: i === 0 ? "2.2cqw" : "0.95cqw",
              letterSpacing: i === 0 ? "-0.01em" : "0.18em",
              textTransform: i === 0 ? "none" : "uppercase",
              lineHeight: 1.25,
              color: palette.ink,
              opacity: i === 0 ? 0.9 : 0.55,
              marginTop: i === 0 ? 0 : 6,
              textShadow: "0 2px 24px rgba(0,0,0,0.45)",
            }}
          >
            {word}
          </div>
        ))}
      </div>
      <span aria-hidden style={{display: "none"}}>{frames}</span>
    </AbsoluteFill>
  );
};

/** Film grain: a static dot pattern shifted a pixel per frame (cheap, no per-frame rerender of pixels). */
const Grain: React.FC<{frame: number}> = ({frame}) => {
  const x = (frame * 7) % 120;
  const y = (frame * 3) % 120;
  return (
    <AbsoluteFill
      style={{
        opacity: 0.055,
        backgroundImage:
          "radial-gradient(rgba(255,255,255,0.9) 0.5px, transparent 0.6px), radial-gradient(rgba(0,0,0,0.9) 0.5px, transparent 0.6px)",
        backgroundSize: "3px 3px, 5px 5px",
        backgroundPosition: `${x}px ${y}px, ${-y}px ${x}px`,
        mixBlendMode: "overlay",
      }}
    />
  );
};

/** Pull a few meaningful words out of a prompt for the typographic layer. */
export function promptKeywords(prompt: string, limit = 3): string[] {
  const stop = new Set([
    "a", "an", "the", "of", "with", "and", "in", "on", "at", "to", "for", "from", "while", "very",
    "is", "are", "into", "soft", "gentle", "illustration", "style", "scene", "wide", "shot",
    "background", "foreground", "cinematic", "lighting", "composition",
  ]);
  return prompt
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 3 && !stop.has(w))
    .slice(0, limit);
}

/**
 * A complete generative scene. `seed` defaults to the prompt so identical prompts render identically.
 */
export const GenerativeScene: React.FC<{
  prompt: string;
  title?: string;
  frames: number;
  accentOverride?: string;
  seed?: string;
}> = ({prompt, title, frames, accentOverride, seed}) => {
  const frame = useCurrentFrame();
  const source = seed ?? prompt;
  const hash = hashPrompt(source);
  const base = PALETTES[hash % PALETTES.length];
  const palette: Palette = accentOverride ? {...base, accent: accentOverride} : base;
  const keywords = promptKeywords(prompt);
  const zoom = interpolate(frame, [0, Math.max(1, frames)], [1, 1.06], {extrapolateRight: "clamp"});

  return (
    <AbsoluteFill style={{overflow: "hidden"}}>
      <AbsoluteFill style={{transform: `scale(${zoom})`, transformOrigin: "50% 55%"}}>
        <Sky palette={palette} frame={frame} frames={frames} hash={hash} />
        <Subject palette={palette} frame={frame} frames={frames} hash={hash} />
        <Motes palette={palette} frame={frame} frames={frames} hash={hash} />
      </AbsoluteFill>
      <TypographicLayer
        palette={palette}
        frame={frame}
        frames={frames}
        hash={hash}
        keywords={keywords}
        title={title}
      />
      <Grain frame={frame} />
      <span aria-hidden style={{display: "none"}}>{round(zoom * 1000)}</span>
    </AbsoluteFill>
  );
};
