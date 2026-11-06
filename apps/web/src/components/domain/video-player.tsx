"use client";

import {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {Player, type PlayerRef} from "@remotion/player";
import {ChevronLeft, ChevronRight, Film, Pause, Play, SkipBack, Timer} from "lucide-react";

import {StoryboardVideo} from "@video/Video";
import type {StoryboardProps, StoryboardScene, VideoSpec} from "@video/types";
import {getTemplate} from "@video/catalogue";
import {buildTimeline} from "@video/timeline";

import {buttonStyles as btn} from "@/components/ui/button";
import {StatusChip} from "@/components/ui/status";
import {cn} from "@/lib/utils";

/**
 * Remotion `<Player>` bound to the same composition the renderer runs.
 *
 * Props arrive from the API already resolved (asset URLs rewritten to the authenticated file proxy),
 * so the preview is byte-for-byte the storyboard that `renderMedia()` will produce. Scene navigation
 * seeks to exact frame boundaries from the shared `buildTimeline()` maths.
 */
export function VideoPlayer({
  spec,
  className,
  initialFrame = 0,
  onSceneChange,
}: {
  spec: VideoSpec;
  className?: string;
  initialFrame?: number;
  onSceneChange?: (scene: StoryboardScene | null) => void;
}) {
  const playerRef = useRef<PlayerRef>(null);
  const template = getTemplate(spec.templateId);
  const timeline = useMemo(() => buildTimeline(spec), [spec]);
  const [frame, setFrame] = useState(initialFrame);
  const [playing, setPlaying] = useState(false);

  const inputProps: StoryboardProps = useMemo(() => ({spec}), [spec]);

  const seek = useCallback((target: number) => {
    playerRef.current?.seekTo(Math.max(0, Math.min(timeline.totalFrames - 1, target)));
  }, [timeline.totalFrames]);

  const activeIndex = useMemo(() => {
    let current = -1;
    timeline.scenes.forEach((placed, i) => {
      if (frame >= placed.from) current = i;
    });
    return current;
  }, [frame, timeline.scenes]);

  useEffect(() => {
    const player = playerRef.current;
    if (!player) return;
    const onFrame = (e: {detail: {frame: number}}) => setFrame(e.detail.frame);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    player.addEventListener("frameupdate", onFrame);
    player.addEventListener("play", onPlay);
    player.addEventListener("pause", onPause);
    return () => {
      player.removeEventListener("frameupdate", onFrame);
      player.removeEventListener("play", onPlay);
      player.removeEventListener("pause", onPause);
    };
  }, []);

  useEffect(() => {
    onSceneChange?.(activeIndex >= 0 ? timeline.scenes[activeIndex].scene : null);
  }, [activeIndex, onSceneChange, timeline.scenes]);

  const fps = spec.fps;
  const currentScene = timeline.scenes[activeIndex];
  const seconds = (frame / fps).toFixed(1);

  return (
    <div className={cn("border border-ink bg-ink", className)}>
      <div className="relative bg-black">
        <Player
          ref={playerRef}
          component={StoryboardVideo}
          inputProps={inputProps}
          durationInFrames={timeline.totalFrames}
          compositionWidth={spec.width}
          compositionHeight={spec.height}
          fps={fps}
          style={{width: "100%", aspectRatio: `${spec.width} / ${spec.height}`}}
          controls
          clickToPlay
          doubleClickToFullscreen
          spaceKeyToPlayOrPause
          acknowledgeRemotionLicense
          errorFallback={({error}) => (
            <div className="flex h-full flex-col items-center justify-center gap-2 bg-[#FBEBEA] p-6 text-center">
              <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#9B2C28]">preview failed</p>
              <p className="max-w-[46ch] text-[12.5px] text-ink">{error.message}</p>
            </div>
          )}
        />
      </div>

      {/* scene strip: click to seek, current scene highlighted */}
      <div className="scroll-thin flex gap-px overflow-x-auto border-t border-ink bg-white">
        {timeline.introFrames > 0 && (
          <SceneChip
            label="intro"
            sub={`${(timeline.introFrames / fps).toFixed(1)}s`}
            active={frame < timeline.bodyStart}
            onClick={() => seek(0)}
            accent={spec.accent}
          />
        )}
        {timeline.scenes.map((placed, i) => (
          <SceneChip
            key={placed.scene.id}
            label={String(placed.scene.index).padStart(2, "0")}
            sub={`${(placed.durationInFrames / fps).toFixed(1)}s`}
            title={placed.scene.title ?? placed.scene.caption ?? undefined}
            active={i === activeIndex}
            onClick={() => seek(placed.from)}
            accent={spec.accent}
          />
        ))}
        {timeline.outroFrames > 0 && (
          <SceneChip
            label="outro"
            sub={`${(timeline.outroFrames / fps).toFixed(1)}s`}
            active={frame >= timeline.totalFrames - timeline.outroFrames}
            onClick={() => seek(timeline.totalFrames - timeline.outroFrames)}
            accent={spec.accent}
          />
        )}
      </div>

      {/* transport + timeline readout */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white px-3 py-2">
        <div className="flex items-center gap-1.5">
          <IconButton label="Previous scene" onClick={() => seek((timeline.scenes[Math.max(0, activeIndex - 1)] ?? timeline.scenes[0]).from)}>
            <ChevronLeft className="size-3.5" />
          </IconButton>
          <IconButton
            label={playing ? "Pause" : "Play"}
            onClick={(e) => playerRef.current?.toggle(e)}
          >
            {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
          </IconButton>
          <IconButton label="Next scene" onClick={() => seek((timeline.scenes[Math.min(timeline.scenes.length - 1, activeIndex + 1)] ?? timeline.scenes[0]).from)}>
            <ChevronRight className="size-3.5" />
          </IconButton>
          <IconButton label="Restart" onClick={() => seek(0)}>
            <SkipBack className="size-3.5" />
          </IconButton>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[9.5px] uppercase tracking-[0.12em] text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <Timer className="size-3" /> {seconds}s / {(timeline.totalFrames / fps).toFixed(1)}s
          </span>
          <span className="flex items-center gap-1.5">
            <Film className="size-3" /> {spec.width}×{spec.height} · {fps} fps
          </span>
          <span>frame {frame} / {timeline.totalFrames - 1}</span>
          {currentScene && <StatusChip tone="outline">scene {String(currentScene.scene.index).padStart(2, "0")}</StatusChip>}
          <span className="text-subtle">{template.name}</span>
        </div>
      </div>

      <div className="h-[3px] w-full bg-muted" aria-hidden>
        <div
          className="h-full bg-ink"
          style={{width: `${Math.min(100, (frame / Math.max(1, timeline.totalFrames - 1)) * 100)}%`}}
        />
      </div>
    </div>
  );
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
  children: React.ReactNode;
}) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick} className={btn("outline", "icon")}>
      {children}
    </button>
  );
}

function SceneChip({
  label,
  sub,
  title,
  active,
  onClick,
  accent,
}: {
  label: string;
  sub: string;
  title?: string;
  active: boolean;
  onClick: () => void;
  accent: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={cn(
        "flex min-w-[74px] flex-col items-start gap-0.5 border-r border-border px-2.5 py-1.5 text-left transition-colors",
        active ? "bg-ink text-white" : "hover:bg-muted",
      )}
    >
      <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em]">
        <span className="size-1.5" style={{backgroundColor: active ? accent : "#a9a9a4"}} />
        {label}
      </span>
      <span className={cn("font-mono text-[9px] uppercase tracking-wider", active ? "text-white/70" : "text-subtle")}>{sub}</span>
    </button>
  );
}
