import * as React from "react";

import { cn } from "@/lib/utils";

const tones = {
  live: "bg-accent text-ink border-ink",
  ink: "bg-ink text-white border-ink",
  idle: "bg-white text-muted-foreground border-border",
  success: "bg-[#F3FBDD] text-[#4B6B0D] border-success",
  warning: "bg-[#FDF4DE] text-[#8A6412] border-warning",
  danger: "bg-[#FBEBEA] text-[#9B2C28] border-danger",
  outline: "bg-white text-ink border-ink",
} as const;

export function StatusChip({
  tone = "idle",
  children,
  className,
  dot = true,
}: {
  tone?: keyof typeof tones;
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-[18px] items-center gap-1.5 border px-1.5 font-mono text-[10px] uppercase tracking-[0.1em] leading-none whitespace-nowrap",
        tones[tone],
        className,
      )}
    >
      {dot && <span className="size-1.5 bg-current" aria-hidden />}
      {children}
    </span>
  );
}

export function workflowTone(status: string): keyof typeof tones {
  switch (status) {
    case "published":
      return "live";
    case "failed":
      return "danger";
    case "cancelled":
      return "idle";
    case "awaiting_approval":
      return "warning";
    case "pending":
    case "planning":
    case "script_generation":
    case "storyboarding":
    case "voice_generation":
    case "visual_generation":
    case "rendering":
    case "quality_checking":
    case "publishing":
      return "ink";
    default:
      return "idle";
  }
}

export function WorkflowStatusChip({ status }: { status: string }) {
  return (
    <StatusChip tone={workflowTone(status)}>
      {status === "awaiting_approval" ? "approval" : status.replaceAll("_", " ")}
    </StatusChip>
  );
}

export function healthTone(health: string): keyof typeof tones {
  if (health === "ok") return "success";
  if (health === "degraded") return "warning";
  if (health === "error") return "danger";
  return "idle";
}

/** Bracket-framed technical tag, e.g. provider chips in the reference request log. */
export function TagBox({
  children,
  emphasis = false,
  className,
}: {
  children: React.ReactNode;
  emphasis?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-[18px] items-center border px-1.5 font-mono text-[10px] uppercase tracking-[0.08em] leading-none",
        emphasis ? "border-dashed border-ink text-ink" : "border-dotted border-muted-foreground text-muted-foreground",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function LiveDot({ tone = "live" }: { tone?: "live" | "warning" | "danger" | "idle" }) {
  const colors = {
    live: "bg-success",
    warning: "bg-warning",
    danger: "bg-danger",
    idle: "bg-border",
  } as const;
  return (
    <span className="relative inline-flex size-2">
      {tone === "live" && (
        <span className={cn("absolute inset-0 animate-ping rounded-full opacity-40", colors[tone])} />
      )}
      <span className={cn("relative size-2 rounded-full", colors[tone])} />
    </span>
  );
}
