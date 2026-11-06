import * as React from "react";

import { cn } from "@/lib/utils";
import type { MetricValue } from "@/lib/types";

import { formatNumber, formatUsd } from "@/lib/format";

type Metric = {
  label: string;
  value: string | number;
  caption?: string;
  accent?: boolean;
  delta?: number | null;
  format?: "number" | "usd" | "percent" | "raw";
};

/**
 * Horizontal bordered metric strip. Mono label, large mono value, mono caption — the reference's
 * "24 / 88% / 3,720" strip. Separators are hairlines; the strip is closed by black rules.
 */
export function MetricStrip({
  metrics,
  className,
  columns,
}: {
  metrics: Metric[];
  className?: string;
  columns?: number;
}) {
  return (
    <div
      className={cn("border-y border-ink bg-white", className)}
      style={
        columns
          ? { display: "grid", gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }
          : undefined
      }
    >
      <div
        className={cn(
          "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8",
          columns && "contents",
        )}
      >
        {metrics.map((m) => (
          <div
            key={m.label}
            className="relative flex min-h-[84px] flex-col justify-between border-border px-3.5 py-3 max-sm:[&:nth-child(2n)]:border-l max-sm:[&:nth-child(n+3)]:border-t sm:[&:not(:first-child)]:border-l lg:[&:nth-child(5)]:border-l-0 xl:[&:nth-child(5)]:border-l [&:not(:first-child)]:max-sm:border-l-0"
          >
            <span className="mono-label leading-none">{m.label}</span>
            <div className="mt-3 min-w-0">
              <div
                className={
                  "mono-value truncate text-ink tracking-[-0.03em] " +
                  (String(m.value).length > 12 ? "text-[13px] leading-tight" : "text-[24px] leading-none md:text-[28px]")
                }
                title={String(m.value)}
              >
                {m.value}
              </div>
              {m.accent && <div className="mt-1.5 h-[3px] w-10 bg-accent" aria-hidden />}
            </div>
            <div className="mt-2 flex items-center justify-between gap-2 font-mono text-[9.5px] uppercase tracking-[0.12em] text-subtle">
              <span className="truncate">{m.caption ?? ""}</span>
              {m.delta !== null && m.delta !== undefined && m.delta !== 0 && (
                <span className={cn("shrink-0", m.delta > 0 ? "text-[#4B6B0D]" : "text-danger")}>
                  {m.delta > 0 ? "▲" : "▼"} {Math.abs(m.delta)}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function metricFrom(
  mv: MetricValue,
  opts: { format?: Metric["format"]; accent?: boolean; big?: boolean } = {},
): Metric {
  const fmt = opts.format ?? "number";
  let value: string;
  switch (fmt) {
    case "usd":
      value = formatUsd(mv.value);
      break;
    case "percent":
      value = `${mv.value}%`;
      break;
    case "raw":
      value = String(mv.value);
      break;
    default:
      value = formatNumber(mv.value);
  }
  return {
    label: mv.label,
    value,
    caption: mv.caption,
    accent: opts.accent,
    delta: mv.previous !== undefined && mv.previous !== null ? Math.round((mv.value - mv.previous) * 10) / 10 : null,
  };
}

/** Compact metric used inside panels. */
export function Stat({
  label,
  value,
  hint,
  accent,
  className,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  accent?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <span className="mono-label">{label}</span>
      <span className={cn("mono-value text-[18px] leading-none", accent ? "text-ink" : "text-ink")}>{value}</span>
      {hint && <span className="font-mono text-[10px] uppercase tracking-wider text-subtle">{hint}</span>}
    </div>
  );
}

export function progressColor(status: string): string {
  if (status === "failed") return "bg-danger";
  if (status === "published") return "bg-success";
  if (status === "awaiting_approval") return "bg-warning";
  return "bg-accent";
}
