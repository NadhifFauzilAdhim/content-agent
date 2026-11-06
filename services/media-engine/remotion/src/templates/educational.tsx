/**
 * Educational — dark navy ground, diagram-friendly split frame, didactic HUD,
 * high-contrast subtitles. Best for explainers where labels must stay readable.
 */

import type React from "react";
import {AbsoluteFill, interpolate, useCurrentFrame} from "remotion";

import {EditorialCard} from "../cards";
import {MONO, SANS, entrance} from "../motion";
import {Backdrop, SceneFrame} from "../scene";
import type {CardProps, SceneRendererProps, TemplateComponent} from "../template";

const COLORS = {accent: "#7FD1FF", background: "#0E1B2A", ink: "#F4F7FA"};

const Scene: React.FC<SceneRendererProps> = ({spec, scene, frames}) => {
  const frame = useCurrentFrame();
  const fade = interpolate(frame, [0, 18], [0, 1], {extrapolateRight: "clamp"});
  const p = entrance("slide", fade);
  return (
    <SceneFrame spec={spec} scene={scene} frames={frames} captionStyle="subtitle">
      {/* Image occupies the left 68%; the right column is a caption panel. */}
      <AbsoluteFill style={{flexDirection: "row"}}>
        <div style={{position: "relative", width: "68%", height: "100%", overflow: "hidden"}}>
          <Backdrop spec={spec} scene={scene} frame={frame} frames={frames} />
        </div>
        <div
          style={{
            width: "32%",
            height: "100%",
            backgroundColor: "#13273B",
            borderLeft: `4px solid ${COLORS.accent}`,
            padding: "8% 5%",
            display: "flex",
            flexDirection: "column",
            justifyContent: "flex-end",
            gap: 14,
          }}
        >
          <span style={{fontFamily: MONO, fontSize: "0.95cqw", letterSpacing: "0.18em", textTransform: "uppercase", color: COLORS.accent, opacity: p.opacity}}>
            {String(scene.index).padStart(2, "0")} · lesson
          </span>
          <span style={{fontFamily: SANS, fontSize: "3.4cqw", lineHeight: 1.1, fontWeight: 600, color: COLORS.ink, opacity: p.opacity, transform: p.transform}}>
            {scene.title ?? spec.title}
          </span>
          <div style={{height: 2, backgroundColor: COLORS.accent, width: `${60 * fade}%`}} />
        </div>
      </AbsoluteFill>
    </SceneFrame>
  );
};

const Title: React.FC<CardProps> = (props) => (
  <EditorialCard {...props} ink={COLORS.ink} background={COLORS.background} accent={COLORS.accent} inverted />
);
const Outro: React.FC<CardProps> = (props) => (
  <EditorialCard {...props} ink={COLORS.ink} background={COLORS.background} accent={COLORS.accent} />
);

export const Educational: TemplateComponent = {
  id: "educational",
  name: "Educational",
  description: "Diagram-friendly split frame with a didactic HUD and high-contrast subtitles.",
  width: 1920,
  height: 1080,
  fps: 30,
  colors: COLORS,
  captionMode: "subtitle",
  defaultTransition: "wipe",
  transitionDurationS: 0.5,
  Title,
  Outro,
  Scene,
};
