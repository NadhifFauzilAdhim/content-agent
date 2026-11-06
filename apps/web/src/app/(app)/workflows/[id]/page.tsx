import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowUpRight, CircleSlash, ListChecks, RotateCw, ScrollText } from "lucide-react";

import { ApiError, resources } from "@/lib/api";
import { formatUsd, formatWhen, relativeTime } from "@/lib/format";
import { ToastAction } from "@/components/domain/actions";
import { PipelineRail } from "@/components/domain/pipeline";
import { buttonStyles } from "@/components/ui/button";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { StatusChip, TagBox, WorkflowStatusChip } from "@/components/ui/status";
import { DataTable, TD, TH, THead, TR } from "@/components/ui/table";

export const metadata = { title: "Workflow" };

const ACTIVE = new Set(["pending", "planning", "script_generation", "storyboarding", "voice_generation", "visual_generation", "rendering", "quality_checking", "publishing"]);

export default async function WorkflowDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let wf;
  try {
    wf = await resources.workflow(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  // Retry covers both real failures and runs stranded mid-stage (the process executing them died).
  // Terminal runs (cancelled, awaiting approval, published) need a new run instead.
  const terminal = ["cancelled", "awaiting_approval", "published"].includes(wf.status);
  const retryable = !terminal && wf.retry_count < 2;
  const cancellable = ACTIVE.has(wf.status) || wf.status === "awaiting_approval";
  const totalTokens = wf.tasks.reduce((s, t) => s + t.tokens_in + t.tokens_out, 0);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Workflows", href: "/workflows" }, { label: wf.workflow_key }]}
        title={wf.project_title ?? "Production run"}
        description={
          wf.error_message ? (
            <span className="text-danger">{wf.error_message}</span>
          ) : (
            <>
              Channel <span className="text-ink">{wf.channel_name}</span> · trigger <span className="text-ink">{wf.trigger}</span> ·
              current agent <span className="text-ink">{wf.current_agent_key ?? "—"}</span>
            </>
          )
        }
        meta={
          <>
            <WorkflowStatusChip status={wf.status} />
            <span>retry {wf.retry_count}/2</span>
          </>
        }
        actions={
          <>
            <Link href="/workflows" className={buttonStyles("ghost", "md")}>
              <ArrowLeft className="!size-3" /> runs
            </Link>
            {cancellable && (
              <ToastAction
                path={`/workflows/${wf.id}/cancel`}
                method="POST"
                success="Workflow cancelled"
                confirm="Cancel this run? In-flight rendering cannot be undone."
                variant="danger"
              >
                <CircleSlash className="!size-3" /> cancel
              </ToastAction>
            )}
            {retryable && (
              <ToastAction
                path={`/workflows/${wf.id}/retry`}
                method="POST"
                success="Retry queued"
                variant="accent"
              >
                <RotateCw className="!size-3" /> retry run
              </ToastAction>
            )}
            {wf.project_id && (
              <Link href={`/content/${wf.project_id}`} className={buttonStyles("primary", "md")}>
                open content <ArrowUpRight className="!size-3" />
              </Link>
            )}
          </>
        }
      />

      <div className="mt-5">
        <PipelineRail stage={wf.status === "published" ? "published" : wf.stage} status={wf.status} />
      </div>

      <div className="mt-5">
        <MetricStrip
          metrics={[
            { label: "progress", value: `${wf.progress}%`, caption: "pipeline", accent: ACTIVE.has(wf.status) },
            { label: "tasks", value: String(wf.tasks.length), caption: `${wf.tasks.filter((t) => t.status === "failed").length} failed` },
            { label: "cost", value: formatUsd(wf.cost_usd, 3), caption: "attributed" },
            { label: "tokens", value: totalTokens ? totalTokens.toLocaleString() : "—", caption: "llm usage" },
            { label: "started", value: wf.started_at ? formatWhen(wf.started_at) : "—", caption: "queued" },
            { label: "finished", value: wf.completed_at ? formatWhen(wf.completed_at) : "—", caption: "completion" },
            { label: "stage", value: wf.stage.replaceAll("_", " "), caption: "current", accent: true },
            { label: "run id", value: wf.workflow_key, caption: wf.trigger },
          ]}
        />
      </div>

      <Section>
        <SectionTitle title="Task timeline" index="01" caption={`${wf.tasks.length} attempts`} />
        {wf.tasks.length === 0 ? (
          <p className="py-4 text-[13px] text-muted-foreground">
            No task has started yet. The runner picks up pending runs within a few seconds.
          </p>
        ) : (
          <ol className="relative mt-1 border-l border-border pl-0">
            {wf.tasks.map((t) => (
              <li key={t.id} className="relative ml-4 border-b border-border py-2.5 pl-4 last:border-b-0">
                <span
                  className={
                    "absolute -left-[4.5px] top-4 size-2 border " +
                    (t.status === "succeeded"
                      ? "border-success bg-success"
                      : t.status === "failed"
                        ? "border-danger bg-danger"
                        : t.status === "running"
                          ? "border-ink bg-accent"
                          : "border-border bg-white")
                  }
                  aria-hidden
                />
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-subtle">{String(t.step_index).padStart(2, "0")}</span>
                    <span className="text-[13px] font-medium">{t.name}</span>
                    <TagBox>{t.agent_key}</TagBox>
                    {t.attempt > 1 && <TagBox emphasis>attempt {t.attempt}</TagBox>}
                  </div>
                  <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    {t.provider && <span>{t.provider}</span>}
                    {t.model && <span className="normal-case tracking-normal">{t.model}</span>}
                    {t.duration_ms !== null && <span className="tabular">{(t.duration_ms / 1000).toFixed(1)}s</span>}
                    {t.cost_usd > 0 && <span className="tabular">{formatUsd(t.cost_usd, 4)}</span>}
                    <StatusChip
                      tone={t.status === "succeeded" ? "success" : t.status === "failed" ? "danger" : t.status === "running" ? "live" : "idle"}
                      dot={false}
                    >
                      {t.status}
                    </StatusChip>
                  </div>
                </div>
                {t.error && (
                  <pre className="mt-2 max-h-24 overflow-auto whitespace-pre-wrap border-l-2 border-danger bg-[#FBEBEA] px-2 py-1.5 font-mono text-[10.5px] text-[#9B2C28]">
                    {t.error}
                  </pre>
                )}
              </li>
            ))}
          </ol>
        )}
      </Section>

      <Section>
        <SectionTitle
          title="Event log"
          index="02"
          caption={`${wf.logs.length} entries`}
          actions={<ScrollText className="size-3.5 text-muted-foreground" />}
        />
        <div className="border border-border bg-paper">
          <div className="max-h-[420px] overflow-y-auto scroll-thin">
            <DataTable minWidth="640px">
              <THead>
                <TH>at</TH>
                <TH>level</TH>
                <TH>event</TH>
              </THead>
              <tbody>
                {wf.logs.map((l) => (
                  <TR key={l.id}>
                    <TD mono className="whitespace-nowrap text-muted-foreground">{formatWhen(l.at)}</TD>
                    <TD>
                      <span
                        className={
                          "font-mono text-[9.5px] uppercase tracking-wider " +
                          (l.level === "error" ? "text-danger" : l.level === "warning" ? "text-[#8A6412]" : "text-muted-foreground")
                        }
                      >
                        {l.level}
                      </span>
                    </TD>
                    <TD className="text-[12px]">{l.message}</TD>
                  </TR>
                ))}
                {wf.logs.length === 0 && (
                  <TR>
                    <TD className="py-4 text-muted-foreground" align="center">No events recorded yet</TD>
                  </TR>
                )}
              </tbody>
            </DataTable>
          </div>
        </div>
      </Section>

      <Section className="pb-6">
        <SectionTitle title="Input reference" index="03" caption="brief snapshot" />
        <pre className="max-h-72 overflow-auto border border-border bg-paper px-3 py-2 font-mono text-[11px] leading-relaxed text-ink">
{JSON.stringify(wf.input, null, 2)}
        </pre>
        <p className="mt-2 flex items-center gap-2 font-mono text-[9.5px] uppercase tracking-wider text-subtle">
          <ListChecks className="size-3" /> outputs are stored per task · assets are content-addressed
          {wf.completed_at && <span>· completed {relativeTime(wf.completed_at)}</span>}
        </p>
      </Section>
    </>
  );
}
