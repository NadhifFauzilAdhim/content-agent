import Link from "next/link";
import {
  ArrowUpRight,
  Bot,
  CheckSquare,
  CircleSlash,
  Coins,
  Film,
  Radio,
  Rocket,
  TriangleAlert,
  Workflow as WorkflowIcon,
} from "lucide-react";

import { assetUrl, resources } from "@/lib/api";
import { formatUsd, formatWhen, relativeTime } from "@/lib/format";
import type { Overview } from "@/lib/types";
import { AgentTrafficMap, StatusStrip } from "@/components/domain/agent-traffic-map";
import { EditorialAreaChart } from "@/components/domain/charts";
import { RefreshButton, RunProduction } from "@/components/domain/actions";
import { Button, buttonStyles } from "@/components/ui/button";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { EmptyState, SetupState } from "@/components/ui/states";
import { LiveDot, StatusChip, TagBox, WorkflowStatusChip } from "@/components/ui/status";
import { DataTable, TD, TH, THead, TR } from "@/components/ui/table";

export const dynamic = "force-dynamic";

function toneFor(status: string) {
  if (["published", "approved"].includes(status)) return "live" as const;
  if (status === "failed" || status === "rejected") return "danger" as const;
  if (status === "awaiting_approval") return "warning" as const;
  if (status === "in_production") return "ink" as const;
  return "idle" as const;
}

export default async function OverviewPage() {
  const [overview, status] = await Promise.all([
    resources.overview(),
    resources.systemStatus().catch(() => null),
  ]);
  const t = overview.totals;
  const mockProviders = overview.providers.filter((p) => p.is_mock && p.is_enabled);
  const realProviders = overview.providers.filter((p) => !p.is_mock && p.is_enabled);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Overview" }]}
        title="Control"
        italic="room"
        description="Every channel, agent and render in one operational view. Production is triggered by the scheduler or by hand; nothing publishes without a recorded approval."
        meta={
          <>
            <span className="flex items-center gap-1.5">
              <LiveDot tone={t.active_workflows.value > 0 ? "live" : "idle"} />
              {t.active_workflows.value > 0 ? "factory working" : "factory idle"}
            </span>
            <span className="text-subtle">upd {formatWhen(status?.time ?? new Date().toISOString())}</span>
          </>
        }
        actions={
          <>
            <RefreshButton />
            <Link href="/approvals" className={buttonStyles("secondary", "md")}>
              <CheckSquare className="!size-3" /> review queue
              {t.pending_approvals.value > 0 && (
                <span className="ml-1 bg-accent px-1 font-mono text-[10px] text-ink">{t.pending_approvals.value}</span>
              )}
            </Link>
            <RunProduction
              channels={overview.channels.map((c) => ({ id: c.id, name: c.name }))}
            />
          </>
        }
      />

      {/* KPI strip */}
      <div className="mt-6">
        <MetricStrip
          metrics={[
            { label: "channels", value: String(t.channels.value), caption: "active workspace", accent: t.channels.value === 0 },
            { label: "generated", value: String(t.generated.value), caption: "last 30d", delta: t.generated.value - (t.generated.previous ?? 0) },
            { label: "published", value: String(t.published.value), caption: "last 30d", delta: t.published.value - (t.published.previous ?? 0) },
            { label: "approvals", value: String(t.pending_approvals.value), caption: "awaiting review", accent: t.pending_approvals.value > 0 },
            { label: "active runs", value: String(t.active_workflows.value), caption: "in production" },
            { label: "failed", value: String(t.failed.value), caption: "last 30d", delta: t.failed.value - (t.failed.previous ?? 0) },
            { label: "ai spend", value: formatUsd(t.spend.value), caption: "month to date" },
            { label: "success", value: `${t.success_rate.value}%`, caption: "completed runs" },
          ]}
        />
      </div>

      {/* system strip */}
      {status && (
        <div className="border-b border-ink">
          <StatusStrip system={overview.system} />
        </div>
      )}

      {/* mock / setup notice */}
      {mockProviders.length > 0 && realProviders.length === 0 && (
        <div className="mt-4">
          <SetupState
            title="Running on mock providers"
            description="Content, voices and images come from deterministic mock adapters so the pipeline can be exercised end-to-end. Titles are prefixed “MOCK” and nothing pretends to be real output. Connect OpenAI, Gemini, Cartesia or ElevenLabs to produce publishable content."
            steps={[
              { label: "Add a real LLM provider (OpenAI or Gemini) with an API key" },
              { label: "Add a TTS provider (Cartesia or ElevenLabs) and an image provider" },
              { label: "Bind agents to those providers in Agents" },
              { label: "Connect the channel’s YouTube account before approving a publish" },
            ]}
            action={{ label: "Configure providers", href: "/providers" }}
          />
        </div>
      )}

      {/* traffic map + activity */}
      <Section>
        <SectionTitle
          title="Production traffic"
          index="01"
          caption="agent routing · 30 days"
          actions={
            <Link href="/agents" className={buttonStyles("outline", "sm")}>
              agent registry <ArrowUpRight className="!size-3" />
            </Link>
          }
        />
        <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
          <AgentTrafficMap
            agents={overview.agent_activity}
            channels={overview.recent_projects}
            flows={overview.channels}
            activityCount={t.generated.value}
          />
          <div className="border border-border bg-white">
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <span className="mono-label">fig. 02 — production activity · 14d</span>
              <span className="flex items-center gap-3 font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
                <span className="flex items-center gap-1"><span className="h-[2px] w-3 bg-ink" /> created</span>
                <span className="flex items-center gap-1"><span className="h-[2px] w-3 bg-[#A8D83E]" /> published</span>
              </span>
            </div>
            <div className="px-2 pt-3">
              <EditorialAreaChart
                data={overview.production_activity}
                series={[
                  { key: "created", label: "Created" },
                  { key: "published", label: "Published" },
                ]}
                height={196}
              />
            </div>
            <div className="grid grid-cols-3 divide-x divide-border border-t border-border">
              {[
                { label: "created 14d", value: overview.production_activity.reduce((s, d) => s + d.created, 0) },
                { label: "published 14d", value: overview.production_activity.reduce((s, d) => s + d.published, 0) },
                { label: "spend mtd", value: formatUsd(t.spend.value) },
              ].map((s) => (
                <div key={s.label} className="px-3 py-2">
                  <p className="mono-label">{s.label}</p>
                  <p className="mono-value mt-1 text-[16px]">{s.value}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Section>

      {/* workflows + projects */}
      <Section>
        <SectionTitle
          title="Recent production"
          index="02"
          caption="latest workflows and content"
          actions={
            <Link href="/workflows" className={buttonStyles("outline", "sm")}>
              all workflows <ArrowUpRight className="!size-3" />
            </Link>
          }
        />
        <div className="grid gap-6 xl:grid-cols-[1.15fr_1fr]">
          <div>
            <div className="flex items-center justify-between border-b border-ink pb-1.5">
              <span className="mono-label text-ink">workflows</span>
              <span className="mono-label text-subtle">{overview.recent_workflows.length} shown</span>
            </div>
            {overview.recent_workflows.length === 0 ? (
              <EmptyState
                className="mt-3"
                title="No workflows yet"
                description="Start a production to see the planner, writer, storyboard, voice, visuals, render and QC stages run in sequence."
                action={{ label: "Open channels", href: "/channels" }}
                icon="inbox"
              />
            ) : (
              <DataTable minWidth="640px">
                <THead>
                  <TH>run</TH>
                  <TH>topic</TH>
                  <TH>stage</TH>
                  <TH align="right">progress</TH>
                  <TH align="right">when</TH>
                </THead>
                <tbody>
                  {overview.recent_workflows.map((w) => (
                    <TR key={w.id} className="relative">
                      <TD mono>
                        <Link href={`/workflows/${w.id}`} className="block font-mono text-[11px] hover:underline">
                          {w.workflow_key}
                        </Link>
                        <span className="flex items-center gap-1.5 pt-1">
                          <TagBox>{w.trigger}</TagBox>
                          <span className="font-mono text-[9.5px] uppercase tracking-wider text-subtle">{w.channel_name}</span>
                        </span>
                      </TD>
                      <TD className="max-w-[220px]">
                        <span className="line-clamp-2 text-[12.5px]">{w.project_title ?? "—"}</span>
                      </TD>
                      <TD>
                        <WorkflowStatusChip status={w.status} />
                      </TD>
                      <TD align="right" mono>
                        <span className="inline-flex items-center gap-2">
                          <span className="hidden h-1 w-10 bg-muted sm:block" aria-hidden>
                            <span
                              className="block h-1 bg-accent"
                              style={{ width: `${w.progress}%` }}
                            />
                          </span>
                          {w.progress}%
                        </span>
                      </TD>
                      <TD align="right" mono className="text-muted-foreground">
                        {relativeTime(w.created_at)}
                      </TD>
                    </TR>
                  ))}
                </tbody>
              </DataTable>
            )}
          </div>

          <div>
            <div className="flex items-center justify-between border-b border-ink pb-1.5">
              <span className="mono-label text-ink">content</span>
              <Link href="/content" className="mono-label text-ink hover:underline">library →</Link>
            </div>
            {overview.recent_projects.length === 0 ? (
              <EmptyState
                className="mt-3"
                title="The library is empty"
                description="Projects appear here once a production reaches the planning stage. Each project holds the script, storyboard, assets, render and QC report."
              />
            ) : (
              <ul className="divide-y divide-border">
                {overview.recent_projects.map((p) => (
                  <li key={p.id}>
                    <Link href={`/content/${p.id}`} className="group flex gap-3 py-2.5">
                      <div className="relative h-[54px] w-24 shrink-0 overflow-hidden border border-border bg-muted">
                        {p.thumbnail_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={assetUrl(p.thumbnail_url)} alt="" className="size-full object-cover" />
                        ) : (
                          <div className="grid size-full place-items-center">
                            <Film className="size-4 text-subtle" />
                          </div>
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-medium text-ink group-hover:underline group-hover:underline-offset-2">
                          {p.title}
                        </p>
                        <p className="mt-0.5 flex items-center gap-2 font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
                          <TagBox>{p.channel_name}</TagBox>
                          <span>{p.format}</span>
                          <span>{relativeTime(p.created_at)}</span>
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <StatusChip tone={toneFor(p.status)}>{p.status.replaceAll("_", " ")}</StatusChip>
                        <span className="mono-value text-[10px] text-muted-foreground">
                          {p.qc_score !== null ? `qc ${p.qc_score}` : "—"}
                        </span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Section>

      {/* providers + system */}
      <Section className="pb-4">
        <SectionTitle
          title="Providers & system"
          index="03"
          caption="live integration health"
          actions={
            <Link href="/providers" className={buttonStyles("outline", "sm")}>
              provider registry <ArrowUpRight className="!size-3" />
            </Link>
          }
        />
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <div className="flex items-center justify-between border-b border-border pb-1.5">
              <span className="mono-label text-ink">ai providers</span>
              <span className="mono-label text-subtle">
                {overview.providers.filter((p) => p.is_enabled && !p.is_mock).length} real ·{" "}
                {overview.providers.filter((p) => p.is_enabled && p.is_mock).length} mock
              </span>
            </div>
            <div className="divide-y divide-border">
              {(["llm", "tts", "image", "youtube"] as const).map((kind) => {
                const rows = overview.providers.filter((p) => p.kind === kind);
                if (rows.length === 0) return null;
                return (
                  <div key={kind} className="py-2">
                    <p className="mono-label mb-1.5 px-0.5">{kind}</p>
                    <ul className="grid gap-1 sm:grid-cols-2">
                      {rows.map((p) => (
                        <li
                          key={p.id}
                          className="flex items-center justify-between gap-2 border border-border px-2 py-1"
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-[12px] leading-tight">{p.name}</span>
                            <span className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
                              {p.is_mock ? "mock" : p.health === "ok" ? "ready" : "needs key"}
                            </span>
                          </span>
                          <StatusChip
                            tone={p.is_mock ? "idle" : p.health === "ok" ? "success" : p.health === "error" ? "danger" : "idle"}
                            dot={false}
                          >
                            {p.is_mock ? "mock" : p.health}
                          </StatusChip>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
              {overview.providers.length === 0 && (
                <p className="py-4 text-[12.5px] text-muted-foreground">
                  No providers registered. <Link href="/providers" className="underline underline-offset-2">Add one</Link>.
                </p>
              )}
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between border-b border-border pb-1.5">
              <span className="mono-label text-ink">services</span>
              <Link href="/settings" className="mono-label text-ink hover:underline">system →</Link>
            </div>
            <ul className="divide-y divide-border">
              {Object.entries(overview.system).map(([key, s]) => (
                <li key={key} className="flex items-center gap-3 py-2">
                  <span className="w-4 shrink-0">
                    {s.status === "ok" ? (
                      <span className="block size-1.5 rounded-full bg-success" />
                    ) : s.status === "paused" ? (
                      <CircleSlash className="size-3 text-warning" />
                    ) : (
                      <TriangleAlert className="size-3 text-muted-foreground" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[12.5px] capitalize">{key}</p>
                    <p className="truncate font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
                      {s.detail}
                    </p>
                  </div>
                  {s.status !== "ok" && (
                    <Link
                      href={key === "youtube" ? "/channels" : "/providers"}
                      className="shrink-0 whitespace-nowrap font-mono text-[9.5px] uppercase tracking-wider text-ink underline underline-offset-2"
                    >
                      fix →
                    </Link>
                  )}
                </li>
              ))}
            </ul>
            {status && (
              <div className="mt-3 grid grid-cols-3 divide-x divide-border border border-border">
                <div className="px-2.5 py-2">
                  <p className="mono-label">scheduler</p>
                  <p className="mt-1 text-[12px]">{status.scheduler.enabled ? "enabled" : "disabled"}</p>
                </div>
                <div className="px-2.5 py-2">
                  <p className="mono-label">next run</p>
                  <p className="mt-1 mono-value text-[11px]">{formatWhen(status.scheduler.next_run_at)}</p>
                </div>
                <div className="px-2.5 py-2">
                  <p className="mono-label">schedules</p>
                  <p className="mt-1 mono-value text-[11px]">{status.scheduler.active_schedules}</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </Section>

      {/* footnote actions */}
      <div className="mt-8 flex flex-wrap gap-2 border-t border-border pt-4">
        {[
          { href: "/channels", icon: Radio, label: "Channels & schedules" },
          { href: "/agents", icon: Bot, label: "Agent configuration" },
          { href: "/workflows", icon: WorkflowIcon, label: "Workflow monitor" },
          { href: "/costs", icon: Coins, label: "Cost ledger" },
          { href: "/providers", icon: Rocket, label: "Provider registry" },
        ].map((l) => (
          <a key={l.href} href={l.href} className={buttonStyles("ghost", "sm")}>
            <l.icon className="!size-3" /> {l.label}
          </a>
        ))}
      </div>
    </>
  );
}

export type { Overview };
export { Button };
