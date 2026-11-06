import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { resources } from "@/lib/api";
import { formatDuration, formatUsd, formatWhen } from "@/lib/format";
import { RefreshButton } from "@/components/domain/actions";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { EmptyState } from "@/components/ui/states";
import { StatusChip } from "@/components/ui/status";

export const metadata = { title: "Approvals" };

export default async function ApprovalsPage() {
  const [pending, all] = await Promise.all([resources.approvals("pending"), resources.approvals("")]);
  const decided = all.filter((a) => a.status !== "pending");

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Approvals" }]}
        title="Human"
        italic="in the loop"
        description="Publishing is gated by a recorded human decision by default. Each request carries the QC score, duration, cost and proposed metadata so the reviewer can decide without leaving the queue."
        actions={<RefreshButton />}
      />

      <div className="mt-6">
        <MetricStrip
          metrics={[
            { label: "pending", value: String(pending.length), caption: "awaiting decision", accent: pending.length > 0 },
            { label: "approved", value: String(decided.filter((a) => a.status === "approved").length), caption: "all time" },
            { label: "rejected", value: String(decided.filter((a) => a.status === "rejected").length), caption: "all time" },
            { label: "expired", value: String(decided.filter((a) => a.status === "expired").length), caption: "timed out" },
          ]}
        />
      </div>

      <Section>
        <SectionTitle title="Review queue" index="01" caption={`${pending.length} requests`} />
        {pending.length === 0 ? (
          <EmptyState
            className="mt-3"
            title="Nothing to review"
            description="When a production finishes rendering and passes quality control, it appears here with everything needed to approve or reject it."
            action={{ label: "Open workflows", href: "/workflows" }}
          />
        ) : (
          <ul className="mt-1 grid gap-4 lg:grid-cols-2">
            {pending.map((a) => {
              const meta = a.summary.metadata ?? {};
              return (
                <li key={a.id} className="border border-ink bg-white shadow-[3px_3px_0_0_var(--accent)]">
                  <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
                    <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-muted-foreground">
                      {a.channel_name} · {formatWhen(a.created_at)}
                    </span>
                    <StatusChip tone="warning" dot={false}>pending</StatusChip>
                  </div>
                  <div className="px-3 py-3">
                    <p className="font-serif text-[22px] leading-tight">{meta.title ?? a.project_title}</p>
                    {meta.description && <p className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-muted-foreground">{meta.description}</p>}
                    <div className="mt-3 grid grid-cols-3 divide-x divide-border border border-border">
                      <div className="px-2 py-1.5">
                        <p className="mono-label">qc score</p>
                        <p className="mono-value text-[15px]">{a.summary.qc_score ?? "—"}</p>
                      </div>
                      <div className="px-2 py-1.5">
                        <p className="mono-label">duration</p>
                        <p className="mono-value text-[15px]">{formatDuration(a.summary.duration_s)}</p>
                      </div>
                      <div className="px-2 py-1.5">
                        <p className="mono-label">cost</p>
                        <p className="mono-value text-[15px]">{formatUsd(a.summary.cost_usd, 3)}</p>
                      </div>
                    </div>
                    {meta.thumbnail_text && (
                      <p className="mt-2 font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
                        thumbnail · “{meta.thumbnail_text}”
                      </p>
                    )}
                  </div>
                  <div className="flex items-center justify-between border-t border-border px-3 py-2">
                    <Link
                      href={`/content/${a.project_id}`}
                      className="font-mono text-[10px] uppercase tracking-wider text-ink underline underline-offset-2 hover:no-underline"
                    >
                      review content <ExternalLink className="inline size-2.5" />
                    </Link>
                    {a.workflow_id && (
                      <Link href={`/workflows/${a.workflow_id}`} className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground hover:text-ink">
                        workflow →
                      </Link>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      {decided.length > 0 && (
        <Section className="pb-8">
          <SectionTitle title="Decision history" index="02" caption={`${decided.length} recorded`} />
          <ul className="divide-y divide-border border-y border-border">
            {decided.slice(0, 20).map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="min-w-0">
                  <span className="block truncate text-[12.5px]">{a.project_title}</span>
                  <span className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
                    {a.channel_name} · decided {formatWhen(a.decided_at)}
                    {a.decision_note ? ` · “${a.decision_note}”` : ""}
                  </span>
                </span>
                <StatusChip tone={a.status === "approved" ? "live" : a.status === "rejected" ? "danger" : "idle"}>{a.status}</StatusChip>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}
