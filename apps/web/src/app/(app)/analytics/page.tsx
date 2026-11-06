import { resources } from "@/lib/api";
import { formatCompact, formatNumber, relativeTime } from "@/lib/format";
import { EditorialAreaChart } from "@/components/domain/charts";
import { RefreshButton } from "@/components/domain/actions";
import { SetupState } from "@/components/ui/states";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { StatusChip, TagBox } from "@/components/ui/status";
import { DataTable, TD, TH, THead, TR } from "@/components/ui/table";
import { SyncAnalytics } from "./sync";

export const metadata = { title: "Analytics" };

export default async function AnalyticsPage() {
  const [analytics, integrations] = await Promise.all([resources.analytics(), resources.integrations()]);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Analytics" }]}
        title="Audience"
        italic="signals"
        description="Performance collected from YouTube Analytics and Data APIs. Insights feed content planning only when measured data exists — there is no synthetic benchmark."
        meta={<StatusChip tone={analytics.configured ? "live" : "idle"} dot={false}>{analytics.configured ? "collecting" : "no data"}</StatusChip>}
        actions={
          <>
            <RefreshButton />
            <SyncAnalytics disabled={!integrations.google_oauth_configured} />
          </>
        }
      />

      <div className="mt-6">
        <MetricStrip
          metrics={[
            { label: "views", value: formatCompact(analytics.totals.views), caption: "latest snapshot" },
            { label: "watch time", value: `${formatCompact(analytics.totals.watch_time_minutes)}m`, caption: "minutes" },
            { label: "avg duration", value: `${Math.round(analytics.totals.avg_view_duration_s)}s`, caption: "weighted" },
            { label: "subscribers", value: formatNumber(analytics.totals.subscribers_gained), caption: "gained" },
            { label: "ctr", value: analytics.totals.ctr ? `${analytics.totals.ctr}%` : "—", caption: "impressions" },
            { label: "videos", value: String(analytics.videos.length), caption: "tracked" },
            { label: "snapshots", value: String(analytics.trend.length), caption: "trend days" },
            { label: "source", value: analytics.configured ? "live" : "none", caption: "youtube analytics", accent: analytics.configured },
          ]}
        />
      </div>

      {!analytics.configured && (
        <div className="mt-4">
          <SetupState
            title={integrations.google_oauth_configured ? "No analytics collected yet" : "YouTube analytics are not connected"}
            description={analytics.detail}
            steps={[
              { label: "Connect a channel’s Google account (Channels → YouTube)", done: false },
              { label: "Grant youtube.readonly + yt-analytics.readonly scopes", done: integrations.google_oauth_configured },
              { label: "Run “sync from youtube” to capture a snapshot", done: false },
            ]}
            action={{ label: "Open channels", href: "/channels" }}
          />
        </div>
      )}

      <Section>
        <SectionTitle title="Views trend" index="01" caption="snapshot days" />
        {analytics.trend.length > 0 ? (
          <EditorialAreaChart data={analytics.trend} series={[{ key: "views", label: "Views" }]} height={240} />
        ) : (
          <div className="flex h-[180px] items-center justify-center border border-dashed border-border bg-paper font-mono text-[10px] uppercase tracking-[0.14em] text-subtle">
            no snapshots — nothing is charted until data exists
          </div>
        )}
      </Section>

      <Section className="pb-8">
        <SectionTitle title="Videos" index="02" caption={`${analytics.videos.length} tracked`} />
        <DataTable minWidth="760px">
          <THead>
            <TH>video</TH>
            <TH>status</TH>
            <TH align="right">views</TH>
            <TH align="right">watch time</TH>
            <TH align="right">avg duration</TH>
            <TH align="right">subs</TH>
            <TH align="right">published</TH>
          </THead>
          <tbody>
            {analytics.videos.map((v) => (
              <TR key={v.id}>
                <TD>
                  <a href={v.url} target="_blank" rel="noreferrer" className="block max-w-[380px] truncate text-[12.5px] hover:underline">
                    {v.title}
                  </a>
                  <span className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">{v.youtube_video_id}</span>
                </TD>
                <TD>
                  {v.is_mock ? <StatusChip tone="idle" dot={false}>mock upload</StatusChip> : <StatusChip tone="live" dot={false}>live</StatusChip>}
                </TD>
                <TD align="right" mono>{v.views === null ? "—" : formatCompact(v.views)}</TD>
                <TD align="right" mono className="text-muted-foreground">{v.watch_time_minutes === null ? "—" : `${Math.round(v.watch_time_minutes)}m`}</TD>
                <TD align="right" mono className="text-muted-foreground">{v.avg_view_duration_s === null ? "—" : `${Math.round(v.avg_view_duration_s)}s`}</TD>
                <TD align="right" mono className="text-muted-foreground">{v.subscribers_gained ?? "—"}</TD>
                <TD align="right" mono className="text-muted-foreground">{relativeTime(v.published_at)}</TD>
              </TR>
            ))}
            {analytics.videos.length === 0 && (
              <TR>
                <TD align="center" className="py-6 text-muted-foreground">
                  <span className="block">No published videos tracked yet</span>
                </TD>
              </TR>
            )}
          </tbody>
        </DataTable>
        <p className="mt-3 font-mono text-[9.5px] uppercase tracking-wider text-subtle">
          <TagBox>note</TagBox> impressions & CTR require channel-owner analytics dimensions and are reported only when available
        </p>
      </Section>
    </>
  );
}
