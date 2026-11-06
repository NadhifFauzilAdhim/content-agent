"use client";

import { cn } from "@/lib/utils";

const STAGES = [
  { key: "planning", label: "plan", agent: "content_planner" },
  { key: "script_generation", label: "script", agent: "script_writer" },
  { key: "storyboarding", label: "board", agent: "storyboard" },
  { key: "voice_generation", label: "voice", agent: "voice_generation" },
  { key: "visual_generation", label: "visuals", agent: "visual_generation" },
  { key: "rendering", label: "render", agent: "video_production" },
  { key: "quality_checking", label: "qc", agent: "quality_control" },
  { key: "seo", label: "seo", agent: "seo_metadata" },
  { key: "awaiting_approval", label: "approval", agent: "quality_control" },
  { key: "publishing", label: "publish", agent: "publishing" },
] as const;

function stageIndex(stage: string): number {
  if (stage === "published") return STAGES.length;
  // the seo agent leaves the workflow stage at quality_checking; approval is its own stage
  const normalised = stage === "seo_metadata" ? "seo" : stage;
  const idx = STAGES.findIndex((s) => s.key === normalised);
  return idx === -1 ? 0 : idx;
}

/**
 * PipelineRail — ten stages as bordered cells joined by hairlines.
 * completed = lime band · current = black frame + lime fill · failed = red · pending = muted.
 */
export function PipelineRail({
  stage,
  status,
  compact = false,
}: {
  stage: string;
  status: string;
  compact?: boolean;
}) {
  const current = stageIndex(stage);
  const failed = status === "failed";
  const cancelled = status === "cancelled";
  const done = status === "published";

  return (
    <div
      className={cn(
        "grid border border-border bg-white",
        compact ? "grid-cols-10" : "grid-cols-5 md:grid-cols-10",
      )}
      role="list"
      aria-label="Production pipeline"
    >
      {STAGES.map((s, i) => {
        const isCurrent = i === current && !done && !failed && !cancelled;
        const isDone = done || i < current;
        const isFailCell = failed && i === current;
        return (
          <div
            key={s.key}
            role="listitem"
            aria-current={isCurrent ? "step" : undefined}
            title={`${s.label} · ${s.agent}`}
            className={cn(
              "relative flex flex-col justify-between border-border px-1.5 py-1.5 [&:not(:first-child)]:border-l",
              compact ? "min-h-[34px]" : "min-h-[46px] max-md:[&:not(:first-child)]:border-l-0 max-md:[&:nth-child(5n+1)]:border-l-0",
              isCurrent && "border border-ink",
              isFailCell && "bg-[#FBEBEA]",
              isDone && !failed && "bg-accent-soft/40",
            )}
          >
            <span
              className={cn(
                "font-mono text-[9px] uppercase leading-none tracking-[0.08em]",
                isDone ? "text-ink" : isCurrent ? "text-ink" : "text-subtle",
                compact && "text-[8px]",
              )}
            >
              {String(i + 1).padStart(2, "0")}
            </span>
            <span
              className={cn(
                "font-mono uppercase leading-none tracking-[0.06em]",
                compact ? "text-[9px]" : "text-[10px]",
                isDone ? "text-ink" : isCurrent ? "font-medium text-ink" : isFailCell ? "text-danger" : "text-muted-foreground",
              )}
            >
              {s.label}
            </span>
            {(isDone || isCurrent) && (
              <span
                className={cn(
                  "absolute inset-x-0 bottom-0 h-[3px]",
                  isFailCell ? "bg-danger" : isDone ? "bg-success" : "bg-accent",
                )}
                aria-hidden
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

export function stageLabel(stage: string): string {
  return STAGES.find((s) => s.key === stage)?.label ?? stage.replaceAll("_", " ");
}

export { STAGES };
