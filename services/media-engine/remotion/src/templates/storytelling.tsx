/**
 * Storytelling — cinematic letterbox, slow Ken Burns, serif overlay titles.
 * The narration carries the scene; titles are centred and drift upward.
 */

import type React from "react";
import {AbsoluteFill, interpolate, useCurrentFrame} from "remotion";

import {EditorialCard} from "../cards";
import {MONO, SERIF, entrance} from "../motion";
import {Backdrop, SceneFrame} from "../scene";
import type {CardProps, SceneRendererProps, TemplateComponent} from "../template";

const COLORS = {accent: "#E8C36A", background: "#0B0B0B", ink: "#F5F1E8"};
const BAR = "11.5%";

const Scene: React.FC<SceneRendererProps> = ({spec, scene, frames}) => {
  const frame = useCurrentFrame();
  const fade = interpolate(frame, [0, 26], [0, 1], {extrapolateRight: "clamp"});
  const p = entrance("fade", fade);
  return (
    <SceneFrame spec={spec} scene={scene} frames={frames} captionStyle="overlay-title">
      <Backdrop spec={spec} scene={scene} frame={frame} frames={frames} />
      <AbsoluteFill style={{background: "linear-gradient(to bottom, rgba(0,0,0,0.45), rgba(0,0,0,0.1) 40%, rgba(0,0,0,0.55))"}} />
      {/* letterbox */}
      <div style={{position: "absolute", left: 0, right: 0, top: 0, height: BAR, backgroundColor: "#000"}} />
      <div style={{position: "absolute", left: 0, right: 0, bottom: 0, height: BAR, backgroundColor: "#000"}} />
      <div style={{position: "absolute", left: "4.5%", top: `calc(${BAR} + 5.2%)`, opacity: p.opacity}}>
        <span style={{fontFamily: MONO, fontSize: "0.95cqw", letterSpacing: "0.22em", textTransform: "uppercase", color: COLORS.accent}}>
          {String(scene.index).padStart(2, "0")}
        </span>
      </div>
      {scene.title ? (
        <div
          style={{
            position: "absolute",
            left: "4.5%",
            right: "4.5%",
            top: `calc(${BAR} + 2.2%)`,
            fontFamily: SERIF,
            fontSize: "2.2cqw",
            fontStyle: "italic",
            color: COLORS.ink,
            opacity: fade * 0.9,
          }}
        >
          {scene.title}
        </div>
      ) : null}
    </SceneFrame>
  );
};

const Title: React.FC<CardProps> = (props) => (
  <EditorialCard {...props} ink={COLORS.ink} background="#000000" accent={COLORS.accent} inverted />
);
const Outro: React.FC<CardProps> = (props) => (
  <EditorialCard {...props} ink={COLORS.ink} background="#000000" accent={COLORS.accent} />
);

export const Storytelling: TemplateComponent = {
  id: "storytelling",
  name: "Storytelling",
  description: "Cinematic letterbox, slow Ken Burns, serif overlay titles.",
  width: 1920,
  height: 1080,
  fps: 30,
  colors: COLORS,
  captionMode: "overlay-title",
  defaultTransition: "fade",
  transitionDurationS: 1.1,
  Title,
  Outro,
  Scene,
};
