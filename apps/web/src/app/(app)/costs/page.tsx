import Link from "next/link";

import { resources } from "@/lib/api";
import { formatUsd } from "@/lib/format";
import { EditorialAreaChart } from "@/components/domain/charts";

const NON_BILLABLE = new Set(["mock", "rules"]);
import { RefreshButton } from "@/components/domain/actions";
import { Pencil } from "lucide-react";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { DataTable, TD, TH, THead, TR } from "@/components/ui/table";
import { BudgetEditor } from "./budget-editor";

export const metadata = { title: "Costs" };

export default async function CostsPage() {
  const costs = await resources.costs();
  const budget = costs.budget_usd;
  const used = budget ? Math.min(100, (costs.month_usd / budget) * 100) : 0;
  const change =
    costs.previous_month_usd > 0
      ? Math.round(((costs.month_usd - costs.previous_month_usd) / costs.previous_month_usd) * 100)
      : null;

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Costs" }]}
        title="Cost"
        italic="ledger"
        description="Every provider call writes one usage row with model, tokens, latency and cost computed from the configured price list. Spend shown here is measured, not estimated."
        actions={<RefreshButton />}
      />

      <div className="mt-6">
        <MetricStrip
          metrics={[
            { label: "month to date", value: formatUsd(costs.month_usd), caption: budget ? `of ${formatUsd(budget)} budget` : "no budget set", accent: true },
            { label: "previous month", value: formatUsd(costs.previous_month_usd), caption: "full month" },
            { label: "change", value: change === null ? "—" : `${change > 0 ? "+" : ""}${change}%`, caption: "month over month" },
            { label: "budget used", value: budget ? `${Math.round(used)}%` : "—", caption: budget ? "remaining" : "unset" },
            { label: "per video min", value: costs.per_minute_usd === null ? "—" : formatUsd(costs.per_minute_usd, 3), caption: "all time" },
            { label: "providers", value: String(costs.by_provider.filter((r) => !NON_BILLABLE.has(r.provider)).length), caption: "billable" },
            { label: "agents", value: String(new Set(costs.by_agent.map((r) => r.agent)).size), caption: "ran" },
            { label: "models", value: String(costs.by_model.filter((r) => !NON_BILLABLE.has(r.model)).length), caption: "billable" },
          ]}
        />
      </div>

      {budget && (
        <div className="border-b border-border py-3">
          <div className="mb-1 flex items-center justify-between font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
            <span>budget utilisation</span>
            <span>{formatUsd(costs.month_usd)} / {formatUsd(budget)}</span>
          </div>
          <div className="h-2 w-full bg-muted" role="progressbar" aria-valuenow={Math.round(used)} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-2 bg-accent" style={{ width: `${used}%` }} />
          </div>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Section>
          <SectionTitle title="Daily spend" index="01" caption="14 days · usd" />
          <EditorialAreaChart data={costs.daily} series={[{ key: "cost_usd", label: "Cost" }]} height={230} format="usd4" />
        </Section>
        <Section>
          <SectionTitle title="By provider" index="02" caption="month to date" />
          <ul className="divide-y divide-border border-y border-border">
            {costs.by_provider.map((r) => (
              <li key={r.provider} className="flex items-center gap-3 py-2">
                <span className="w-28 shrink-0 font-mono text-[10.5px] uppercase tracking-wider">{r.provider || "—"}</span>
                <span className="h-2 flex-1 bg-muted" aria-hidden>
                  <span className="block h-2 bg-accent" style={{ width: `${Math.max(2, r.share)}%` }} />
                </span>
                <span className="w-24 shrink-0 text-right font-mono text-[10.5px] tabular">
                  {r.cost_usd > 0 ? formatUsd(r.cost_usd, 4) : "no price"}
                </span>
                <span className="w-14 shrink-0 text-right font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  {r.calls} calls
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 font-mono text-[9.5px] uppercase tracking-wider text-subtle">
            mock and rules adapters are counted but never billed · set model prices on the provider
          </p>
        </Section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section>
          <SectionTitle title="By agent" index="03" caption="attribution" />
          <DataTable>
            <THead>
              <TH>agent</TH>
              <TH align="right">calls</TH>
              <TH align="right">tokens</TH>
              <TH align="right">cost</TH>
              <TH align="right">share</TH>
            </THead>
            <tbody>
              {costs.by_agent.map((r) => (
                <TR key={r.agent}>
                  <TD mono>{r.agent}</TD>
                  <TD align="right" mono>{r.calls}</TD>
                  <TD align="right" mono className="text-muted-foreground">{r.tokens.toLocaleString()}</TD>
                  <TD align="right" mono>{formatUsd(r.cost_usd, 4)}</TD>
                  <TD align="right" mono className="text-muted-foreground">{r.share}%</TD>
                </TR>
              ))}
              {costs.by_agent.length === 0 && <TR><TD align="center" className="py-4 text-muted-foreground">No usage</TD></TR>}
            </tbody>
          </DataTable>
        </Section>
        <Section>
          <SectionTitle title="By model" index="04" caption="attribution" />
          <DataTable>
            <THead>
              <TH>model</TH>
              <TH align="right">calls</TH>
              <TH align="right">cost</TH>
              <TH align="right">share</TH>
            </THead>
            <tbody>
              {costs.by_model.map((r) => (
                <TR key={r.model}>
                  <TD mono>{r.model || "—"}</TD>
                  <TD align="right" mono>{r.calls}</TD>
                  <TD align="right" mono>{formatUsd(r.cost_usd, 4)}</TD>
                  <TD align="right" mono className="text-muted-foreground">{r.share}%</TD>
                </TR>
              ))}
              {costs.by_model.length === 0 && <TR><TD align="center" className="py-4 text-muted-foreground">No usage</TD></TR>}
            </tbody>
          </DataTable>
        </Section>
      </div>

      <Section className="pb-8">
        <SectionTitle
          title="Budgets"
          index="05"
          caption="spend guards"
          actions={<Link href="/providers" className="mono-label flex items-center gap-1 text-ink hover:underline"><Pencil className="size-2.5" /> price list lives with providers</Link>}
        />
        <div className="grid gap-6 md:grid-cols-[1fr_1fr]">
          <BudgetEditor monthly={costs.budget_usd} channelCeiling={costs.budgets.channel_ceiling} />
          <div className="border-l border-border pl-4 text-[12.5px] leading-relaxed text-muted-foreground md:block">
            <p>
              <span className="text-ink">Monthly budget</span> — production runs stop with a budget error when
              month-to-date spend reaches this value. The guard runs before every stage.
            </p>
            <p className="mt-2">
              <span className="text-ink">Per-video ceiling</span> — recorded on the channel and surfaced in the
              QC report so a runaway render is visible before approval.
            </p>
            <p className="mt-2 font-mono text-[9.5px] uppercase tracking-wider text-subtle">
              cost = tokens × price/1M · unit-priced providers bill per image, character or upload
            </p>
          </div>
        </div>
      </Section>
    </>
  );
}
