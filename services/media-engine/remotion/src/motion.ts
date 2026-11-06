/**
 * Motion primitives shared by every scene component.
 *
 * All animation is derived from `useCurrentFrame()` and `useVideoConfig()` — no timers, no
 * randomness, no `Date.now()`. A frame therefore renders identically every time, which is what
 * makes previews match the export and renders idempotent.
 */

import type React from "react";
import {Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from "remotion";

import type {EntranceKind, KenBurnsKind} from "./types";

export function clampProgress(frame: number, delay = 0, duration = 18): number {
  return interpolate(frame, [delay, delay + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
}

/** Entrance transform for text/visual elements. Returns style properties to spread. */
export function entrance(
  kind: EntranceKind = "rise",
  progress: number,
): React.CSSProperties {
  const p = Math.max(0, Math.min(1, progress));
  switch (kind) {
    case "none":
      return {};
    case "fade":
      return {opacity: p};
    case "rise":
      return {opacity: p, transform: `translateY(${(1 - p) * 24}px)`};
    case "slide":
      return {opacity: p, transform: `translateX(${(1 - p) * 48}px)`};
    case "scale":
      return {opacity: p, transform: `scale(${0.92 + p * 0.08})`};
    case "typewriter":
      return {opacity: 1};
    default:
      return {opacity: p};
  }
}

/** Ken Burns transform for a still image within a scene of `frames` frames at `fps`. */
export function kenBurns(kind: KenBurnsKind = "in", frame: number, frames: number): string {
  const t = interpolate(frame, [0, Math.max(1, frames)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  switch (kind) {
    case "none":
      return "scale(1.02)";
    case "out":
      return `scale(${1.14 - t * 0.12})`;
    case "pan-left":
      return `scale(1.12) translateX(${(0.02 - t * 0.04) * 100}%)`;
    case "pan-right":
      return `scale(1.12) translateX(${(t * 0.04 - 0.02) * 100}%)`;
    case "in":
    default:
      return `scale(${1.02 + t * 0.1})`;
  }
}

export function useSpringIn(delay = 0, config = {damping: 200, mass: 0.7}): number {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return spring({frame: frame - delay, fps, config, durationInFrames: 26});
}

/** Reveal `text` character by character. `progress` 0..1 over the scene. */
export function typedText(text: string, progress: number, startProgress = 0.05, endProgress = 0.45): string {
  const p = Math.min(1, Math.max(0, (progress - startProgress) / (endProgress - startProgress)));
  const chars = Math.round(text.length * p);
  return text.slice(0, chars);
}

export const MONO = '"IBM Plex Mono", "SFMono-Regular", ui-monospace, monospace';
export const SERIF = '"Instrument Serif", Georgia, "Times New Roman", serif';
export const SANS = 'Geist, "Helvetica Neue", Arial, sans-serif';
