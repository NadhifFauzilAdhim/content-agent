"use client";

/** Data + formatting carried into the client via context, so no function is serialised per render. */

import { createContext, useContext, type ReactNode } from "react";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const STROKE = "#111111";
const GRID = "#E9E9E4";
const ACCENT = "#D6FF45";

export type ChartConfig = {
  kind: "area" | "bar";
  data: Record<string, string | number>[];
  series: { key: string; label: string }[];
  height: number;
  format: "int" | "usd4" | "minutes";
};

const EMPTY_CONFIG: ChartConfig = { kind: "area", data: [], series: [], height: 0, format: "int" };

const ChartContext = createContext<ChartConfig | null>(null);

export function ChartProvider({ config, children }: { config: ChartConfig; children: ReactNode }) {
  return <ChartContext.Provider value={config}>{children}</ChartContext.Provider>;
}

function useFormat(config: ChartConfig) {
  const usd = config.format === "usd4";
  const suffix = config.format === "minutes" ? "m" : "";
  const fmt = (v: number) =>
    `${usd ? "$" : ""}${new Intl.NumberFormat("en-US", { maximumFractionDigits: usd ? 4 : 2 }).format(v)}${suffix}`;
  return { fmt, usd, labelFor: (key: string) => config.series.find((s) => s.key === key)?.label ?? key };
}

const tooltipStyle = {
  borderRadius: 0,
  border: `1px solid ${STROKE}`,
  background: "#FFFFFF",
  boxShadow: `3px 3px 0 0 ${ACCENT}`,
  fontFamily: "var(--font-plex-mono)",
  fontSize: 11,
  padding: "6px 8px",
} as const;

export function ChartCanvas() {
  const config = useContext(ChartContext);
  // call hooks unconditionally, before any early return
  const { fmt, usd, labelFor } = useFormat(config ?? EMPTY_CONFIG);
  if (!config) return null;

  if (config.kind === "bar") {
    return (
      <div style={{ height: config.height }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={config.data} margin={{ top: 4, right: 12, bottom: 0, left: 4 }} layout="vertical" barCategoryGap={6}>
            <CartesianGrid horizontal={false} stroke={GRID} />
            <YAxis dataKey="label" type="category" width={112} tickLine={false} axisLine={false} />
            <XAxis type="number" hide />
            <Tooltip cursor={{ fill: "#F5F5F2" }} contentStyle={tooltipStyle} formatter={(v) => [fmt(Number(v)), ""]} />
            <Bar dataKey="value" fill={ACCENT} stroke={STROKE} strokeWidth={1} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  const primary = config.series[0]?.key ?? "value";
  const gradientId = `fill-${primary.replace(/[^a-z]/gi, "")}`;
  return (
    <div style={{ height: config.height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={config.data} margin={{ top: 8, right: 6, bottom: 0, left: -14 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={ACCENT} stopOpacity={0.85} />
              <stop offset="100%" stopColor={ACCENT} stopOpacity={0.08} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="0" vertical={false} stroke={GRID} />
          <XAxis
            dataKey="date"
            tickFormatter={(v: string) => v.slice(5)}
            tickLine={false}
            axisLine={{ stroke: STROKE, strokeWidth: 1 }}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis tickLine={false} axisLine={false} width={38} allowDecimals={usd} tickFormatter={(v: number) => fmt(v)} />
          <Tooltip
            cursor={{ stroke: STROKE, strokeWidth: 1, strokeDasharray: "3 3" }}
            contentStyle={tooltipStyle}
            labelStyle={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.1em", color: "#888" }}
            formatter={(value, name) => [fmt(Number(value)), labelFor(String(name))]}
          />
          {config.series.map((s, i) => (
            <Area
              key={s.key}
              type="stepAfter"
              dataKey={s.key}
              name={s.key}
              stroke={STROKE}
              strokeWidth={i === 0 ? 1.6 : 1.1}
              fill={i === 0 ? `url(#${gradientId})` : "transparent"}
              strokeDasharray={i > 0 ? "3 3" : undefined}
              dot={false}
              activeDot={{ r: 3, fill: ACCENT, stroke: STROKE }}
              isAnimationActive={false}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
