/**
 * Children's story — soft pastel ground, rounded vignette, sticker-style scene badge.
 * Gentle zoom transitions, warm serif narration lower thirds.
 */

import type React from "react";
import {AbsoluteFill, interpolate, useCurrentFrame} from "remotion";

import {RoundBadgeCard} from "../cards";
import {MONO, entrance} from "../motion";
import {Backdrop, SceneFrame} from "../scene";
import type {CardProps, SceneRendererProps, TemplateComponent} from "../template";

const COLORS = {accent: "#FFB4A2", background: "#FFF6EC", ink: "#2B2B2B"};

const Scene: React.FC<SceneRendererProps> = ({spec, scene, frames}) => {
  const frame = useCurrentFrame();
  const p = entrance("scale", interpolate(frame, [0, 20], [0, 1], {extrapolateRight: "clamp"}));
  return (
    <SceneFrame spec={spec} scene={scene} frames={frames} captionStyle="lower-third">
      <Backdrop spec={spec} scene={scene} frame={frame} frames={frames} />
      <AbsoluteFill
        style={{
          boxShadow: "inset 0 0 0 26px rgba(255,180,162,0.45), inset 0 0 120px 40px rgba(255,246,236,0.35)",
          borderRadius: 36,
          margin: 16,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: "4%",
          top: "4%",
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "8px 16px",
          borderRadius: 999,
          backgroundColor: "#FFFFFF",
          boxShadow: "0 6px 18px rgba(200,140,120,0.25)",
          opacity: p.opacity,
          transform: p.transform,
        }}
      >
        <span style={{width: 10, height: 10, borderRadius: "50%", backgroundColor: "#FF8FA3"}} />
        <span style={{fontFamily: MONO, fontSize: "1cqw", letterSpacing: "0.12em", textTransform: "uppercase", color: "#2B2B2B"}}>
          story · {String(scene.index).padStart(2, "0")}
        </span>
      </div>
    </SceneFrame>
  );
};

const Title: React.FC<CardProps> = (props) => <RoundBadgeCard {...props} {...COLORS} />;
const Outro: React.FC<CardProps> = (props) => <RoundBadgeCard {...props} {...COLORS} />;

export const ChildrensStory: TemplateComponent = {
  id: "childrens-story",
  name: "Children's story",
  description: "Soft pastel ground, rounded vignette, playful sticker badges.",
  width: 1920,
  height: 1080,
  fps: 30,
  colors: COLORS,
  captionMode: "lower-third",
  defaultTransition: "zoom",
  transitionDurationS: 0.75,
  Title,
  Outro,
  Scene,
};
