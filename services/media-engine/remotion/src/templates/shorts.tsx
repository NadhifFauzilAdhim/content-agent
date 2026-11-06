/**
 * Shorts — 9:16. Full-bleed art, stacked title block at the top, chunky subtitles at the bottom,
 * and a progress hairline that reads well on a phone. Optional YouTube Shorts variant uses the
 * editorial lime accent.
 */

import type React from "react";
import {AbsoluteFill, interpolate, useCurrentFrame} from "remotion";

import {MONO, SANS, SERIF, entrance} from "../motion";
import {Backdrop, SceneFrame} from "../scene";
import type {CardProps, SceneRendererProps, TemplateComponent} from "../template";

const SHORTS_COLORS = {accent: "#FF4D2E", background: "#111111", ink: "#FFFFFF"};
const YT_SHORTS_COLORS = {accent: "#D6FF45", background: "#111111", ink: "#FFFFFF"};

function makeScene(colors: {accent: string; ink: string}): React.FC<SceneRendererProps> {
  return ({spec, scene, frames}) => {
    const frame = useCurrentFrame();
    const p = entrance("rise", interpolate(frame, [0, 16], [0, 1], {extrapolateRight: "clamp"}));
    return (
      <SceneFrame spec={spec} scene={scene} frames={frames} captionStyle="subtitle" showBrand={false}>
        <Backdrop spec={spec} scene={scene} frame={frame} frames={frames} />
        <AbsoluteFill style={{background: "linear-gradient(to bottom, rgba(0,0,0,0.55), rgba(0,0,0,0) 35%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.65))"}} />
        <div style={{position: "absolute", left: "7%", right: "7%", top: "9%", opacity: p.opacity, transform: p.transform}}>
          <div style={{height: 6, width: 54, backgroundColor: colors.accent, marginBottom: 16}} />
          <div style={{fontFamily: SANS, fontSize: "6.4cqw", fontWeight: 700, lineHeight: 1.02, letterSpacing: "-0.02em", color: colors.ink}}>
            {scene.title ?? spec.title}
          </div>
        </div>
        <div style={{position: "absolute", right: "7%", top: "9.5%", fontFamily: MONO, fontSize: "2.1cqw", letterSpacing: "0.14em", color: colors.accent}}>
          {String(scene.index).padStart(2, "0")}
        </div>
      </SceneFrame>
    );
  };
}

function makeCard(colors: {accent: string; ink: string; background: string}): (c: CardProps) => React.ReactElement {
  return ({headline, subline, cta, spec, frames}: CardProps) => {
    const frame = useCurrentFrame();
    const p = interpolate(frame, [0, 18], [0, 1], {extrapolateRight: "clamp"});
    void frames;
    return (
      <AbsoluteFill style={{backgroundColor: colors.background, padding: "18% 8%", justifyContent: "center"}}>
        <div style={{width: 72, height: 8, backgroundColor: colors.accent, marginBottom: 26}} />
        <div style={{fontFamily: SERIF, fontSize: "11cqw", lineHeight: 0.95, letterSpacing: "-0.03em", color: colors.ink, opacity: p}}>
          {headline}
        </div>
        {subline ? (
          <div style={{marginTop: 22, fontFamily: SANS, fontSize: "3.4cqw", fontWeight: 500, color: colors.ink, opacity: p * 0.8}}>
            {subline}
          </div>
        ) : null}
        {cta ? (
          <div style={{marginTop: 34, alignSelf: "flex-start", backgroundColor: colors.accent, color: "#111111", padding: "14px 22px", fontFamily: MONO, fontSize: "2.2cqw", letterSpacing: "0.1em", textTransform: "uppercase", opacity: p}}>
            {cta}
          </div>
        ) : null}
        <div style={{position: "absolute", bottom: "7%", left: "8%", fontFamily: MONO, fontSize: "2cqw", letterSpacing: "0.22em", color: colors.ink, opacity: 0.5}}>
          {spec.brand}
        </div>
      </AbsoluteFill>
    );
  };
}

export const Shorts: TemplateComponent = {
  id: "shorts",
  name: "Short-form · vertical",
  description: "9:16 frame with stacked title block and punchy chunky subtitles.",
  width: 1080,
  height: 1920,
  fps: 30,
  colors: SHORTS_COLORS,
  captionMode: "subtitle",
  defaultTransition: "slide-up",
  transitionDurationS: 0.35,
  Title: makeCard(SHORTS_COLORS),
  Outro: makeCard(SHORTS_COLORS),
  Scene: makeScene(SHORTS_COLORS),
};

export const YouTubeShorts: TemplateComponent = {
  ...Shorts,
  id: "youtube-shorts",
  name: "YouTube Shorts",
  description: "9:16 short with the editorial lime identity and an oversized scene index.",
  colors: YT_SHORTS_COLORS,
  Title: makeCard(YT_SHORTS_COLORS),
  Outro: makeCard(YT_SHORTS_COLORS),
  Scene: makeScene(YT_SHORTS_COLORS),
};
