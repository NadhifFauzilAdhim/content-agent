/**
 * Shared card designs (title / outro) reused by templates that want the editorial language with a
 * different palette.
 */

import type React from "react";
import {AbsoluteFill, interpolate, useCurrentFrame} from "remotion";

import {MONO, SERIF} from "./motion";
import type {CardProps} from "./template";

export function EditorialCard({
  spec,
  headline,
  subline,
  cta,
  ink,
  background,
  accent,
  inverted = false,
}: CardProps & {ink: string; background: string; accent: string; inverted?: boolean}) {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [0, 24], [0, 1], {extrapolateRight: "clamp"});
  return (
    <AbsoluteFill style={{backgroundColor: background, padding: "9% 8%", justifyContent: "flex-end"}}>
      <div style={{position: "absolute", top: "8%", left: "8%", display: "flex", alignItems: "center", gap: 10}}>
        <span style={{width: 10, height: 10, backgroundColor: accent}} />
        <span style={{fontFamily: MONO, fontSize: "1.05cqw", letterSpacing: "0.2em", textTransform: "uppercase", color: ink, opacity: 0.7}}>
          {spec.brand}
        </span>
      </div>
      <div style={{borderTop: `2px solid ${ink}`, marginBottom: 14}} />
      <div style={{borderTop: `1px solid ${ink}`, marginBottom: 26, opacity: 0.6}} />
      <div
        style={{
          fontFamily: SERIF,
          fontSize: inverted ? "8.2cqw" : "7.2cqw",
          lineHeight: 0.98,
          letterSpacing: "-0.025em",
          color: ink,
          opacity: p,
          transform: `translateY(${(1 - p) * 22}px)`,
        }}
      >
        {headline}
      </div>
      {subline ? (
        <div style={{marginTop: 16, fontFamily: MONO, fontSize: "1.3cqw", letterSpacing: "0.14em", textTransform: "uppercase", color: ink, opacity: p * 0.65}}>
          {subline}
        </div>
      ) : null}
      {cta ? (
        <div
          style={{
            marginTop: 30,
            alignSelf: "flex-start",
            border: `1px solid ${ink}`,
            backgroundColor: accent,
            color: "#111111",
            padding: "10px 16px",
            fontFamily: MONO,
            fontSize: "1.05cqw",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            opacity: p,
          }}
        >
          {cta}
        </div>
      ) : null}
    </AbsoluteFill>
  );
}

export function RoundBadgeCard({
  spec,
  headline,
  subline,
  cta,
  ink,
  background,
  accent,
  frames,
}: CardProps & {ink: string; background: string; accent: string}) {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [0, 22], [0, 1], {extrapolateRight: "clamp"});
  void frames;
  return (
    <AbsoluteFill style={{backgroundColor: background, alignItems: "center", justifyContent: "center", padding: "10%"}}>
      <div
        style={{
          position: "absolute",
          width: "62%",
          aspectRatio: "1 / 1",
          borderRadius: "50%",
          backgroundColor: accent,
          opacity: 0.35 * p,
          transform: `scale(${0.9 + p * 0.1})`,
        }}
      />
      <div style={{position: "relative", textAlign: "center", fontFamily: SERIF, color: ink, fontSize: "6cqw", lineHeight: 1.05, opacity: p}}>
        {headline}
      </div>
      {subline ? (
        <div style={{position: "relative", marginTop: 18, fontFamily: MONO, fontSize: "1.2cqw", letterSpacing: "0.14em", textTransform: "uppercase", color: ink, opacity: p * 0.7}}>
          {subline}
        </div>
      ) : null}
      {cta ? (
        <div style={{position: "relative", marginTop: 26, borderRadius: 999, backgroundColor: "#111111", color: "#FFFFFF", padding: "12px 22px", fontFamily: MONO, fontSize: "1.05cqw", letterSpacing: "0.1em", textTransform: "uppercase", opacity: p}}>
          {cta}
        </div>
      ) : null}
      <div style={{position: "absolute", bottom: "6%", fontFamily: MONO, fontSize: "1cqw", letterSpacing: "0.2em", color: ink, opacity: 0.5}}>
        {spec.brand}
      </div>
    </AbsoluteFill>
  );
}
