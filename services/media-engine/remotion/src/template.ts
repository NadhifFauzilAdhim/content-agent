/**
 * Template contract.
 *
 * A template contributes three pure renderers — title card, outro card and one storyboard scene —
 * plus its palette and defaults. Everything timing-related (sequence placement, transitions,
 * narration, music, captions) is owned by the engine in `Video.tsx`, so templates can never get
 * out of step with the timeline the API computed.
 */

import type React from "react";

import type {StoryboardScene, VideoSpec} from "./types";

export type SceneRendererProps = {
  spec: VideoSpec;
  scene: StoryboardScene;
  /** Local frame count for this scene (already rounded by the engine). */
  frames: number;
};

export type CardProps = {
  spec: VideoSpec;
  headline: string;
  subline?: string | null;
  cta?: string | null;
  frames: number;
};

export type TemplateComponent = {
  id: string;
  name: string;
  description: string;
  width: number;
  height: number;
  fps: number;
  colors: {accent: string; background: string; ink: string};
  captionMode: "lower-third" | "subtitle" | "overlay-title";
  defaultTransition: "fade" | "cut" | "slide-left" | "slide-up" | "wipe" | "iris" | "zoom";
  transitionDurationS: number;
  Title: React.ComponentType<CardProps>;
  Outro: React.ComponentType<CardProps>;
  Scene: React.ComponentType<SceneRendererProps>;
};
