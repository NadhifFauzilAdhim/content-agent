/** Server-side chart wrappers: pass plain data, formatting stays inside the client chart. */

import { ChartCanvas, ChartProvider, type ChartConfig } from "./chart-data";

type SeriesPoint = { date: string } & Record<string, string | number>;

export function EditorialAreaChart({
  data,
  series,
  height = 200,
  format = "int",
}: {
  data: SeriesPoint[];
  series: { key: string; label: string }[];
  height?: number;
  format?: ChartConfig["format"];
}) {
  const config: ChartConfig = { kind: "area", data, series, height, format };
  return (
    <ChartProvider config={config}>
      <ChartCanvas />
    </ChartProvider>
  );
}

export function BarComparison({
  data,
  height = 180,
  format = "usd4",
}: {
  data: { label: string; value: number }[];
  height?: number;
  format?: ChartConfig["format"];
}) {
  const config: ChartConfig = {
    kind: "bar",
    data: data.map((d) => ({ ...d })),
    series: [{ key: "value", label: "Value" }],
    height,
    format,
  };
  return (
    <ChartProvider config={config}>
      <ChartCanvas />
    </ChartProvider>
  );
}
