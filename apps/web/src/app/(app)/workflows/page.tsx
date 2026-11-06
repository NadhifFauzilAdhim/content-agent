import Link from "next/link";
import { ArrowUpRight, Filter } from "lucide-react";

import { resources } from "@/lib/api";
import { formatUsd, formatWhen, relativeTime } from "@/lib/format";
import type { Workflow } from "@/lib/types";
import { RefreshButton, RunProduction } from "@/components/domain/actions";
import { PipelineRail } from "@/components/domain/pipeline";
import { buttonStyles } from "@/components/ui/button";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { EmptyState } from "@/components/ui/states";
import { StatusChip, TagBox, WorkflowStatusChip } from "@/components/ui/status";
import { DataTable, TD, TH, THead, TR } from "@/components/ui/table";

export const metadata = { title: "Workflows" };

const FILTERS = [
  { key: "all", label: "all" },
  { key: "active", label: "active" },
  { key: "awaiting_approval", label: "awaiting approval" },
  { key: "published", label: "published" },
  { key: "failed", label: "failed" },
];

const ACTIVE = new Set(["pending", "planning", "script_generation", "storyboarding", "voice_generation", "visual_generation", "rendering", "quality_checking", "publishing", "awaiting_approval"]);

export default async function WorkflowsPage({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  const { status: filter = "all" } = await searchParams;
  const [all, channels] = await Promise.all([
    resources.workflows({ limit: "200" }),
    resources.channels(),
  ]);

  const rows =
    filter === "all"
      ? all
      : filter === "active"
        ? all.filter((w) => ACTIVE.has(w.status))
        : all.filter((w) => w.status === filter);

  const active = all.filter((w) => ACTIVE.has(w.status));
  const awaiting = all.filter((w) => w.status === "awaiting_approval");
  const failed = all.filter((w) => w.status === "failed");
  const published = all.filter((w) => w.status === "published");
  const totalCost = all.reduce((s, w) => s + w.cost_usd, 0);
  const successRate = published.length + failed.length > 0 ? Math.round((published.length / (published.length + failed.length)) * 100) : 0;

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Workflows" }]}
        title="Workflow"
        italic="monitor"
        description="Each production is a durable run with a unique key, stage history, per-agent cost and retry budget. Runs survive worker restarts — state lives in the database, never in an open request."
        actions={
          <>
            <RefreshButton />
            <RunProduction channels={channels.map((c) => ({ id: c.id, name: c.name }))} />
          </>
        }
      />

      <div className="mt-6">
        <MetricStrip
          metrics={[
            { label: "runs", value: String(all.length), caption: "all time" },
            { label: "active", value: String(active.length), caption: "in production", accent: active.length > 0 },
            { label: "awaiting", value: String(awaiting.length), caption: "human review", accent: awaiting.length > 0 },
            { label: "published", value: String(published.length), caption: "delivered" },
            { label: "failed", value: String(failed.length), caption: "needs attention" },
            { label: "success", value: `${successRate}%`, caption: "finished runs" },
            { label: "run cost", value: formatUsd(totalCost), caption: "attributed spend" },
            { label: "retries", value: String(all.reduce((s, w) => s + w.retry_count, 0)), caption: "manual + auto" },
          ]}
        />
      </div>

      <Section>
        <SectionTitle
          title="Runs"
          index="01"
          caption={`${rows.length} of ${all.length}`}
          actions={
            <nav className="flex flex-wrap items-center gap-1" aria-label="Filter workflows">
              <Filter className="mr-1 size-3 text-muted-foreground" />
              {FILTERS.map((f) => (
                <Link
                  key={f.key}
                  href={f.key === "all" ? "/workflows" : `/workflows?status=${f.key}`}
                  className={
                    filter === f.key
                      ? "bg-ink px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-white"
                      : "border border-border px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground hover:border-ink hover:text-ink"
                  }
                >
                  {f.label}
                </Link>
              ))}
            </nav>
          }
        />

        {rows.length === 0 ? (
          <EmptyState
            className="mt-3"
            title={all.length === 0 ? "No production runs yet" : "Nothing matches this filter"}
            description={
              all.length === 0
                ? "Run a production to execute the ten-stage pipeline: plan → script → storyboard → voice → visuals → render → QC → SEO → approval → publish."
                : "Try another status filter to see other runs."
            }
            action={all.length === 0 ? { label: "Open channels", href: "/channels" } : undefined}
          />
        ) : (
          <ul className="mt-1 divide-y divide-border">
            {rows.map((w) => (
              <WorkflowRow key={w.id} w={w} />
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}

function WorkflowRow({ w }: { w: Workflow }) {
  return (
    <li className="group grid gap-3 py-4 lg:grid-cols-[220px_minmax(0,1fr)_210px] lg:items-center">
      <div className="min-w-0">
        <Link href={`/workflows/${w.id}`} className="font-mono text-[11.5px] hover:underline underline-offset-2">
          {w.workflow_key}
        </Link>
        <div className="mt-1 flex items-center gap-1.5">
          <WorkflowStatusChip status={w.status} />
          <TagBox>{w.trigger}</TagBox>
        </div>
      </div>
      <div className="min-w-0">
        <p className="truncate text-[13px] font-medium text-ink">
          {w.project_title ?? `${w.channel_name} · untitled`}
        </p>
        <p className="mb-1.5 mt-0.5 flex items-center gap-2 font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
          <span>{w.channel_name}</span>
          <span className="text-subtle">·</span>
          <span>{w.current_agent_key ?? "—"}</span>
          {w.error_message && <span className="truncate text-danger normal-case tracking-normal">{w.error_message.slice(0, 80)}</span>}
        </p>
        <PipelineRail stage={w.stage} status={w.status} compact />
      </div>
      <div className="flex items-center justify-between gap-3 lg:flex-col lg:items-end">
        <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          <span className="tabular">{w.progress}%</span>
          <span className="tabular">{formatUsd(w.cost_usd, 3)}</span>
          <span className="tabular">{relativeTime(w.created_at)}</span>
        </div>
        <Link href={`/workflows/${w.id}`} className={buttonStyles("outline", "xs", "opacity-80 group-hover:opacity-100")}>
          inspect <ArrowUpRight className="!size-2.5" />
        </Link>
      </div>
      {w.started_at && (
        <span className="sr-only">started {formatWhen(w.started_at)}</span>
      )}
    </li>
  );
}

export type { Workflow };
export { DataTable, TD, TH, THead, TR, StatusChip };
