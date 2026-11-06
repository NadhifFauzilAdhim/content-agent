"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, ChevronRight } from "lucide-react";

import type { Overview } from "@/lib/types";
import { cn } from "@/lib/utils";
import { StatusChip, TagBox } from "@/components/ui/status";

type Node = Overview["agent_activity"][number];

const CLIENTS = [
  { key: "schedule", label: "scheduler", detail: "cron per channel" },
  { key: "manual", label: "operator", detail: "manual runs" },
  { key: "approval", label: "reviewer", detail: "approval loop" },
] as const;

export function AgentTrafficMap({
  agents,
  channels,
  flows,
  activityCount,
}: {
  agents: Overview["agent_activity"];
  channels: Overview["recent_projects"];
  flows: { id: string; name: string; handle: string; runs: number; is_active: boolean }[] | undefined;
  activityCount: number;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const nodes = useMemo(() => {
    const byKey = new Map(agents.map((a) => [a.key, a]));
    const order = [
      "content_planner",
      "script_writer",
      "storyboard",
      "voice_generation",
      "visual_generation",
      "video_production",
      "quality_control",
      "seo_metadata",
      "publishing",
      "analytics",
    ];
    return order.map((key) => byKey.get(key)).filter(Boolean) as Node[];
  }, [agents]);

  const active = selected ? nodes.find((n) => n.key === selected) : null;
  const totalRuns = nodes.reduce((s, n) => s + n.executions, 0);

  const channelList = flows && flows.length > 0 ? flows : channels.slice(0, 3).map((p) => ({
    id: p.id,
    name: p.channel_name,
    handle: p.channel_name.toLowerCase().replace(/\s+/g, "-"),
    runs: 0,
    is_active: true,
  }));

  return (
    <div className="border border-border bg-white">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <span className="mono-label">fig. 01 — agent traffic · 30d</span>
        <span className="mono-label text-subtle">{totalRuns} task runs</span>
      </div>
      <div className="relative">
        <div className="line-grid pointer-events-none absolute inset-0 opacity-70" aria-hidden />
        <div className="relative grid gap-3 p-3 lg:grid-cols-[minmax(0,0.95fr)_170px_minmax(0,1.45fr)] lg:gap-0">
          {/* clients */}
          <div className="flex flex-col justify-center gap-2">
            <span className="mono-label mb-0.5">input</span>
            {CLIENTS.map((c) => (
              <div key={c.key} className="flex items-center justify-between border border-border bg-white px-2.5 py-1.5">
                <div className="min-w-0">
                  <p className="truncate text-[12.5px] font-medium text-ink">{c.label}</p>
                  <p className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">{c.detail}</p>
                </div>
                <span className="mono-value text-[12px] text-muted-foreground">→</span>
              </div>
            ))}
            <div className="mt-1 flex items-center gap-2 border-y border-border py-1.5">
              <span className="mono-label">channels</span>
              <span className="flex flex-wrap gap-1">
                {channelList.slice(0, 3).map((c) => (
                  <TagBox key={c.id}>{c.handle}</TagBox>
                ))}
                {channelList.length === 0 && <TagBox>none</TagBox>}
              </span>
            </div>
          </div>

          {/* core */}
          <div className="relative flex items-center justify-center py-3">
            <svg className="pointer-events-none absolute inset-0 h-full w-full max-lg:hidden" aria-hidden>
              <defs>
                <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                  <path d="M0,0 L6,3 L0,6 z" fill="#B9D63A" />
                </marker>
              </defs>
              <path d="M0,60 C40,60 40,60 58,60" stroke="#C9DB8C" strokeWidth="1" strokeDasharray="3 3" fill="none" />
              <path d="M120,80 C150,80 150,80 170,80" stroke="#B9D63A" strokeWidth="1.2" strokeDasharray="3 3" fill="none" markerEnd="url(#arrow)" />
            </svg>
            <div className="relative z-10 w-full max-w-[190px] border border-ink bg-ink px-3 py-3 text-white">
              <p className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-white/60">factory core</p>
              <p className="mt-1 font-serif text-[20px] leading-tight">Production</p>
              <p className="mono-value mt-2 text-[11px] text-accent">
                {activityCount} runs
              </p>
              <p className="font-mono text-[9.5px] uppercase tracking-wider text-white/50">
                {nodes.reduce((s, n) => s + n.executions, 0)} tasks
              </p>
            </div>
            <div className="absolute inset-y-2 left-1/2 -z-0 w-[1px] -translate-x-1/2 bg-border lg:hidden" />
          </div>

          {/* agents */}
          <div className="flex flex-col gap-1 lg:pl-4">
            <span className="mono-label mb-0.5 flex justify-between">
              <span>agents</span>
              <span className="text-subtle">success / avg</span>
            </span>
            {nodes.length === 0 && (
              <div className="border border-dashed border-border bg-white px-3 py-4 text-[12px] text-muted-foreground">
                No agent activity yet. Start a production to populate the map.
              </div>
            )}
            {nodes.map((n) => {
              const isSel = selected === n.key;
              return (
                <button
                  key={n.key}
                  type="button"
                  onClick={() => setSelected(isSel ? null : n.key)}
                  aria-pressed={isSel}
                  className={cn(
                    "group relative flex items-center justify-between gap-2 border px-2.5 py-1.5 text-left transition-colors",
                    isSel
                      ? "border-ink bg-white shadow-[3px_3px_0_0_var(--accent)]"
                      : n.executions > 0
                        ? "border-border bg-white hover:border-ink"
                        : "border-border/70 bg-paper hover:border-ink",
                  )}
                >
                  <span
                    className={cn(
                      "absolute -left-[7px] top-1/2 hidden size-[5px] -translate-y-1/2 rounded-full ring-2 ring-white lg:block",
                      n.executions > 0 ? "bg-[#A8D83E]" : "bg-border",
                    )}
                    aria-hidden
                  />
                  <span className="min-w-0">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-[12.5px] font-medium text-ink">{n.name}</span>
                      {isSel && <span className="bg-accent px-1 font-mono text-[8.5px] uppercase tracking-wider">selected</span>}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1.5">
                      <TagBox>{n.stage.replaceAll("_", " ")}</TagBox>
                      <span className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
                        {n.executions} runs
                      </span>
                    </span>
                  </span>
                  <span className={cn("min-w-0 shrink-0 text-right", !n.executions && "opacity-60")}>
                    <span className={cn("mono-value block text-[12px]", n.executions ? "text-ink" : "text-subtle")}>
                      {n.executions ? `${Math.round(n.success_rate)}%` : "—"}
                    </span>
                    <span className="font-mono text-[9px] uppercase tracking-wider text-subtle">
                      {n.executions === 0
                        ? "idle"
                        : n.avg_duration_ms < 1000
                          ? `${n.avg_duration_ms}ms`
                          : `${(n.avg_duration_ms / 1000).toFixed(1)}s`}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-3 py-1.5">
        <div className="flex items-center gap-4 font-mono text-[9.5px] uppercase tracking-[0.12em] text-muted-foreground">
          <span className="flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-[#A8D83E]" /> active</span>
          <span className="flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-border" /> idle</span>
          <span className="flex items-center gap-1.5"><span className="h-0 w-4 border-t border-dashed border-[#B9D63A]" /> routing</span>
          {active && <span className="text-ink">· {active.name}: ${active.cost_usd.toFixed(2)}</span>}
        </div>
        <Link href="/agents" className="flex items-center gap-1 font-mono text-[9.5px] uppercase tracking-[0.12em] text-ink hover:underline">
          configure agents <ArrowUpRight className="size-3" />
        </Link>
      </div>
    </div>
  );
}

export function StatusStrip({ system }: { system: Overview["system"] }) {
  return (
    <div className="grid grid-cols-2 divide-x divide-border border-b border-border sm:grid-cols-3 lg:grid-cols-6">
      {Object.entries(system).map(([key, s]) => (
        <div key={key} className="flex items-center justify-between gap-2 border-b border-border px-3 py-2 last:border-b-0 lg:border-b-0">
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">{key}</span>
          <StatusChip tone={s.status === "ok" ? "success" : s.status === "paused" ? "warning" : "idle"} dot={false}>
            {s.status}
          </StatusChip>
        </div>
      ))}
    </div>
  );
}

export function SystemExplainer({ children }: { children: React.ReactNode }) {
  return <div className="relative">{children}</div>;
}

export function Chevron() {
  return <ChevronRight className="size-3 text-subtle" />;
}
