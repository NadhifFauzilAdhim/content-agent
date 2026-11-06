import Link from "next/link";
import { Film } from "lucide-react";

import { assetUrl, resources } from "@/lib/api";
import { formatDuration, formatUsd, relativeTime } from "@/lib/format";
import type { ProjectStatus } from "@/lib/types";
import { RefreshButton } from "@/components/domain/actions";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { EmptyState } from "@/components/ui/states";
import { StatusChip, TagBox } from "@/components/ui/status";
import { DataTable, TD, TH, THead, TR } from "@/components/ui/table";

export const metadata = { title: "Content" };

const STATUSES: { key: string; label: string }[] = [
  { key: "all", label: "all" },
  { key: "awaiting_approval", label: "awaiting approval" },
  { key: "approved", label: "approved" },
  { key: "published", label: "published" },
  { key: "in_production", label: "in production" },
  { key: "failed", label: "failed" },
];

function tone(status: ProjectStatus) {
  if (status === "published" || status === "approved") return "live" as const;
  if (status === "failed" || status === "rejected") return "danger" as const;
  if (status === "awaiting_approval") return "warning" as const;
  if (status === "in_production") return "ink" as const;
  return "idle" as const;
}

export default async function ContentPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; channel?: string; q?: string }>;
}) {
  const { status = "all", channel = "", q = "" } = await searchParams;
  const [all, channels] = await Promise.all([resources.projects({ limit: "200" }), resources.channels()]);

  const rows = all.filter(
    (p) =>
      (status === "all" || p.status === status) &&
      (!channel || p.channel_id === channel) &&
      (!q || p.title.toLowerCase().includes(q.toLowerCase())),
  );

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Content" }]}
        title="Content"
        italic="library"
        description="Every generated project with its script, storyboard, scene assets, render and quality report. Metadata can be edited before approval; renders are downloadable."
        actions={<RefreshButton />}
      />

      <div className="mt-6">
        <MetricStrip
          metrics={[
            { label: "projects", value: String(all.length), caption: "all time" },
            { label: "awaiting", value: String(all.filter((p) => p.status === "awaiting_approval").length), caption: "approval", accent: true },
            { label: "approved", value: String(all.filter((p) => p.status === "approved").length), caption: "ready to publish" },
            { label: "published", value: String(all.filter((p) => p.status === "published").length), caption: "delivered" },
            { label: "renders", value: String(all.filter((p) => p.status !== "draft").length), caption: "with output" },
            { label: "avg qc", value: avgQc(all.map((p) => p.qc_score)), caption: "quality score" },
            { label: "spend", value: formatUsd(all.reduce((s, p) => s + p.total_cost_usd, 0)), caption: "attributed" },
            { label: "channels", value: String(new Set(all.map((p) => p.channel_id)).size), caption: "producing" },
          ]}
        />
      </div>

      <Section>
        <SectionTitle
          title="Projects"
          index="01"
          caption={`${rows.length} shown`}
          actions={
            <form className="flex flex-wrap items-center gap-1.5" action="/content" method="get">
              <input
                name="q"
                defaultValue={q}
                placeholder="search titles"
                className="h-7 w-44 border border-border bg-white px-2 text-[12px] outline-none focus:border-ink"
                aria-label="Search titles"
              />
              <select name="channel" defaultValue={channel} aria-label="Channel" className="h-7 border border-border bg-white px-1.5 font-mono text-[10px] uppercase tracking-wider outline-none focus:border-ink">
                <option value="">all channels</option>
                {channels.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              <select name="status" defaultValue={status} aria-label="Status" className="h-7 border border-border bg-white px-1.5 font-mono text-[10px] uppercase tracking-wider outline-none focus:border-ink">
                {STATUSES.map((s) => (
                  <option key={s.key} value={s.key}>{s.label}</option>
                ))}
              </select>
              <button type="submit" className="h-7 border border-ink bg-ink px-2 font-mono text-[10px] uppercase tracking-wider text-white hover:bg-accent hover:text-ink">
                filter
              </button>
            </form>
          }
        />

        {rows.length === 0 ? (
          <EmptyState
            className="mt-3"
            title={all.length === 0 ? "No projects yet" : "No projects match"}
            description={
              all.length === 0
                ? "A project is created by the content planner at the start of every production run. Start one from Overview or Workflows."
                : "Clear the search or choose another status filter."
            }
            action={all.length === 0 ? { label: "Go to workflows", href: "/workflows" } : undefined}
          />
        ) : (
          <DataTable minWidth="900px" className="mt-1">
            <THead>
              <TH>project</TH>
              <TH>channel</TH>
              <TH>status</TH>
              <TH align="right">qc</TH>
              <TH align="right">duration</TH>
              <TH align="right">cost</TH>
              <TH align="right">created</TH>
            </THead>
            <tbody>
              {rows.map((p) => (
                <TR key={p.id}>
                  <TD>
                    <Link href={`/content/${p.id}`} className="group flex items-center gap-3 pr-3">
                      <span className="relative grid h-10 w-[68px] shrink-0 place-items-center overflow-hidden border border-border bg-muted">
                        {p.thumbnail_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={assetUrl(p.thumbnail_url)} alt="" className="size-full object-cover" loading="lazy" />
                        ) : (
                          <Film className="size-3.5 text-subtle" />
                        )}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-[13px] font-medium group-hover:underline group-hover:underline-offset-2">
                          {p.title}
                        </span>
                        <span className="mt-0.5 flex items-center gap-1.5">
                          <TagBox>{p.format}</TagBox>
                          <span className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">{p.language}</span>
                        </span>
                      </span>
                    </Link>
                  </TD>
                  <TD className="whitespace-nowrap text-[12.5px] text-muted-foreground">{p.channel_name}</TD>
                  <TD><StatusChip tone={tone(p.status)}>{p.status.replaceAll("_", " ")}</StatusChip></TD>
                  <TD align="right" mono>
                    {p.qc_score !== null ? (
                      <span className={p.qc_score >= 85 ? "" : "text-[#8A6412]"}>{p.qc_score}</span>
                    ) : "—"}
                  </TD>
                  <TD align="right" mono className="text-muted-foreground">{formatDuration(p.estimated_duration_s)}</TD>
                  <TD align="right" mono className="text-muted-foreground">{formatUsd(p.total_cost_usd, 3)}</TD>
                  <TD align="right" mono className="whitespace-nowrap text-muted-foreground">{relativeTime(p.created_at)}</TD>
                </TR>
              ))}
            </tbody>
          </DataTable>
        )}
      </Section>
    </>
  );
}

function avgQc(values: (number | null)[]): string {
  const clean = values.filter((v): v is number => v !== null);
  if (!clean.length) return "—";
  return String(Math.round(clean.reduce((a, b) => a + b, 0) / clean.length));
}
