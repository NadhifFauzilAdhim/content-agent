/**
 * Composition root.
 *
 * Every template is registered as its own composition sharing the same engine component, so the
 * Studio, the Player and `renderMedia()` all use identical code. `calculateMetadata` derives the
 * duration from the storyboard, which means the API does not have to send a frame count.
 */

import type React from "react";
import {Composition, Folder, registerRoot} from "remotion";

import {CATALOGUE, DEFAULT_TEMPLATE} from "./catalogue";
import {StoryboardVideo} from "./Video";
import type {StoryboardProps} from "./types";

const SAMPLE_HINT = "The video is rendered from storyboard props; open the Data panel to edit them.";

function calculateMetadata({props}: {props: StoryboardProps}) {
  const spec = props.spec;
  const fps = spec.fps || 30;
  const overlap = Math.round((spec.transitionDurationS || 0) * fps);
  const sceneFrames = spec.scenes.reduce((total, scene, i) => {
    const frames = Math.max(12, Math.round((scene.durationS / (spec.speed || 1)) * fps));
    const cuts = i === 0 ? 0 : overlap;
    return total + frames - cuts;
  }, 0);
  const intro = spec.intro?.enabled ? Math.round(spec.intro.durationS * fps) : 0;
  const outro = spec.outro?.enabled ? Math.round(spec.outro.durationS * fps) : 0;
  return {
    durationInFrames: Math.max(12, sceneFrames + intro + outro),
    fps,
    width: spec.width || 1920,
    height: spec.height || 1080,
    props,
  };
}

const ROOT_PROPS: StoryboardProps = {
  spec: {
    version: 1,
    title: "The Lantern Path",
    brand: "FACTORY",
    templateId: DEFAULT_TEMPLATE,
    width: 1920,
    height: 1080,
    fps: 30,
    accent: "#D6FF45",
    background: "#FFFFFF",
    ink: "#111111",
    captions: {enabled: true, mode: "lower-third"},
    defaultTransition: "fade",
    transitionDurationS: 0.6,
    intro: {enabled: true, durationS: 2.4, title: "The Lantern Path", subtitle: "A story for curious children"},
    outro: {
      enabled: true,
      durationS: 3,
      headline: "The end.",
      subline: "Mossy keeps the harbour light.",
      cta: "Subscribe for a new story every week.",
    },
    music: {url: null, volume: 0.12, duckUnderNarration: true, fadeInS: 1.2, fadeOutS: 2},
    scenes: [
      {
        id: "m1",
        index: 1,
        title: SAMPLE_HINT,
        imageSrc: null,
        narrationSrc: null,
        durationS: 4.5,
        transition: "fade",
        caption: "The sun went down behind the hill and the harbour turned the colour of pale tea.",
        animation: {kenBurns: "in", entrance: "rise"},
      },
      {
        id: "m2",
        index: 2,
        imageSrc: null,
        narrationSrc: null,
        durationS: 4,
        transition: "fade",
        caption: "Mossy lit a lantern on the tallest post she could find.",
        animation: {kenBurns: "pan-right", entrance: "rise"},
        elements: [{kind: "progress", position: "bottom"}],
      },
      {
        id: "m3",
        index: 3,
        imageSrc: null,
        narrationSrc: null,
        durationS: 4.2,
        transition: "fade",
        caption: "By midnight, every boat could see the way home.",
        animation: {kenBurns: "out", entrance: "scale"},
      },
    ],
  },
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Folder name="Factory">
        {Object.entries(CATALOGUE).map(([id, template]) => (
          <Composition
            key={id}
            id={id}
            component={StoryboardVideo}
            durationInFrames={300}
            fps={template.fps}
            width={template.width}
            height={template.height}
            defaultProps={{
              ...ROOT_PROPS,
              spec: {
                ...ROOT_PROPS.spec,
                templateId: id,
                width: template.width,
                height: template.height,
                fps: template.fps,
                accent: template.colors.accent,
                background: template.colors.background,
                ink: template.colors.ink,
                captions: {enabled: true, mode: template.captionMode},
                defaultTransition: template.defaultTransition,
                transitionDurationS: template.transitionDurationS,
              },
            }}
            calculateMetadata={calculateMetadata}
          />
        ))}
      </Folder>
    </>
  );
};

registerRoot(RemotionRoot);
