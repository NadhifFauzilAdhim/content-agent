import { formatDuration, formatNumber, formatUsd } from "@/lib/format";
import type { TTSUsage } from "@/lib/types";

/** Text-first usage board: bars are hairline/solid ink, the single accent marks the leader. */
export function UsageBoard({ usage }: { usage: TTSUsage }) {
  const providers = Object.entries(usage.by_provider).sort((a, b) => b[1].characters - a[1].characters);
  const models = Object.entries(usage.by_model).sort((a, b) => b[1].characters - a[1].characters).slice(0, 8);
  const days = Object.entries(usage.by_day).sort(([a], [b]) => a.localeCompare(b));
  const maxDay = Math.max(1, ...days.map(([, d]) => d.characters));
  const total = usage.totals;
  const failureRate = total.generations ? (total.failed / total.generations) * 100 : 0;

  return (
    <div className="space-y-7">
      <div className="grid grid-cols-2 border-y border-ink md:grid-cols-4">
        {[
          { label: "characters", value: formatNumber(total.characters), caption: "billed units" },
          { label: "audio", value: formatDuration(total.audio_seconds), caption: "generated duration" },
          { label: "estimated", value: formatUsd(total.estimated_cost_usd, 3), caption: "list price" },
          { label: "actual", value: total.actual_cost_usd ? formatUsd(total.actual_cost_usd, 3) : "—", caption: "provider reported" },
        ].map((m, i) => (
          <div key={m.label} className={`px-3 py-3 ${i > 0 ? "border-l border-border" : ""}`}>
            <p className="mono-label">{m.label}</p>
            <p className="mono-value mt-1 text-[22px] text-ink">{m.value}</p>
            <p className="font-mono text-[9px] uppercase tracking-wider text-subtle">{m.caption}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-8 md:grid-cols-2">
        <div>
          <h3 className="mono-label mb-2 text-ink">by provider</h3>
          <BarList
            rows={providers.map(([name, d]) => ({
              label: name,
              value: d.characters,
              detail: `${formatNumber(d.characters)} chars · ${formatDuration(d.seconds)} · ${formatUsd(d.cost_usd, 3)} · ${(d.avg_latency_ms / 1000).toFixed(1)}s`,
            }))}
          />
        </div>
        <div>
          <h3 className="mono-label mb-2 text-ink">by model</h3>
          <BarList
            rows={models.map(([name, d]) => ({
              label: name,
              value: d.characters,
              detail: `${formatNumber(d.generations)} gen · ${formatUsd(d.cost_usd, 3)}`,
            }))}
          />
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <h3 className="mono-label text-ink">characters per day</h3>
          <span className="font-mono text-[9.5px] uppercase tracking-wider text-subtle">
            {days.length} active day{days.length === 1 ? "" : "s"} · {failureRate.toFixed(0)}% failures
          </span>
        </div>
        <div className="flex h-24 items-end gap-[3px] border-b border-ink" role="img" aria-label="Characters generated per day">
          {days.map(([day, d]) => (
            <div key={day} className="group relative flex-1" title={`${day}: ${formatNumber(d.characters)} chars · ${d.generations} gen`}>
              <div
                className={d.failed > 0 && d.generations === d.failed ? "w-full bg-danger" : "w-full bg-ink group-hover:bg-accent"}
                style={{ height: `${Math.max(2, (d.characters / maxDay) * 96)}px` }}
              />
            </div>
          ))}
        </div>
        <div className="mt-1 flex justify-between font-mono text-[9px] uppercase tracking-wider text-subtle">
          <span>{days[0]?.[0] ?? ""}</span>
          <span>{days[days.length - 1]?.[0] ?? ""}</span>
        </div>
      </div>
    </div>
  );
}

function BarList({ rows }: { rows: { label: string; value: number; detail: string }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="space-y-2">
      {rows.length === 0 && <li className="text-[12px] text-muted-foreground">No data</li>}
      {rows.map((row, i) => (
        <li key={row.label}>
          <div className="flex items-baseline justify-between gap-3">
            <span className="truncate font-mono text-[11.5px] text-ink">{row.label}</span>
            <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{row.detail}</span>
          </div>
          <div className="mt-1 h-[3px] w-full bg-muted">
            <div
              className={i === 0 ? "h-full bg-ink" : "h-full bg-[#9c9c96]"}
              style={{ width: `${Math.max(2, (row.value / max) * 100)}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
