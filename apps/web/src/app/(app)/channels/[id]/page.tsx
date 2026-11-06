import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowUpRight } from "lucide-react";

import { ApiError, resources } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import { RunProduction } from "@/components/domain/actions";
import { buttonStyles } from "@/components/ui/button";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { SetupState } from "@/components/ui/states";
import { StatusChip, TagBox } from "@/components/ui/status";

import { CastEditor, ChannelSettingsForm, ScheduleEditor, YoutubeConnect } from "./channel-forms";

export const metadata = { title: "Channel" };

export default async function ChannelDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let channel;
  try {
    channel = await resources.channel(id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
  const [schedules, integrations, projects] = await Promise.all([
    resources.schedules(id).catch(() => []),
    resources.integrations(),
    resources.projects({ channel: id, limit: "5" }),
  ]);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Channels", href: "/channels" }, { label: channel.name }]}
        title={channel.name}
        description={channel.description ?? "No description yet."}
        meta={
          <>
            <StatusChip tone={channel.is_active ? "live" : "idle"} dot={false}>{channel.is_active ? "active" : "paused"}</StatusChip>
            <span>{channel.handle}</span>
          </>
        }
        actions={
          <>
            <Link href="/channels" className={buttonStyles("ghost", "md")}>
              <ArrowLeft className="!size-3" /> channels
            </Link>
            <RunProduction channels={[{ id: channel.id, name: channel.name }]} label="run production" />
          </>
        }
      />

      <div className="mt-6">
        <MetricStrip
          metrics={[
            { label: "produced", value: String(channel.production_count), caption: "projects" },
            { label: "published", value: String(channel.published_count), caption: "videos" },
            { label: "next run", value: formatWhen(channel.next_run_at), caption: schedules[0]?.timezone ?? "no schedule" },
            { label: "language", value: channel.language.toUpperCase(), caption: channel.audience },
            { label: "format", value: channel.video_format, caption: "aspect" },
            { label: "duration", value: `${Math.round((channel.settings?.target_duration_seconds ?? 0) / 60)}m`, caption: "target" },
            { label: "quality", value: `${channel.settings?.min_quality_score ?? 85}`, caption: "min score" },
            { label: "cast", value: String(channel.characters.length), caption: "characters" },
          ]}
        />
      </div>

      <div className="mt-6 grid gap-8 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div>
          <Section className="!mt-0">
            <SectionTitle title="Identity & policy" index="01" caption="saved to the channel context" />
            <ChannelSettingsForm channel={channel} />
          </Section>

          <Section>
            <SectionTitle title="Cast" index="02" caption="locked character descriptions" />
            <CastEditor channel={channel} />
          </Section>

          <Section>
            <SectionTitle title="Production schedule" index="03" caption="timezone-aware · one run per slot" />
            <ScheduleEditor channelId={channel.id} schedules={schedules} />
          </Section>
        </div>

        <div className="space-y-6">
          <div className="border border-ink">
            <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
              <span className="mono-label text-ink">youtube account</span>
              <StatusChip tone={channel.youtube_channel_id ? "live" : "warning"} dot={false}>
                {channel.youtube_channel_id ? "connected" : "not connected"}
              </StatusChip>
            </div>
            <div className="px-3 py-3">
              {channel.youtube_channel_id ? (
                <>
                  <p className="text-[13px]">{channel.youtube_channel_title ?? channel.youtube_channel_id}</p>
                  <p className="mt-0.5 font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
                    since {formatWhen(channel.youtube_connected_at)} · scopes upload, read, analytics
                  </p>
                </>
              ) : integrations.google_oauth_configured ? (
                <p className="text-[12.5px] leading-relaxed text-muted-foreground">
                  Connect this channel&apos;s Google account to enable uploads and analytics. Tokens are encrypted
                  at rest and refreshed automatically.
                </p>
              ) : (
                <p className="text-[12.5px] leading-relaxed text-muted-foreground">
                  Google OAuth is not configured on the server. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET,
                  restart the API, then connect here. Approvals are recorded either way; publishing stays blocked.
                </p>
              )}
              <div className="mt-3">
                <YoutubeConnect channelId={channel.id} connected={!!channel.youtube_channel_id} oauthConfigured={integrations.google_oauth_configured} />
              </div>
            </div>
          </div>

          {!channel.youtube_channel_id && (
            <SetupState
              title="Publishing is blocked"
              description="Approving a video is recorded, but the publishing agent cannot upload until this channel is linked. The workflow surfaces the exact reason."
              action={{ label: "Provider settings", href: "/providers" }}
            />
          )}

          <div className="border border-border">
            <div className="border-b border-border px-3 py-1.5">
              <span className="mono-label text-ink">recent projects</span>
            </div>
            <ul className="divide-y divide-border">
              {projects.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-2 px-3 py-2">
                  <Link href={`/content/${p.id}`} className="min-w-0 flex-1 truncate text-[12.5px] hover:underline">
                    {p.title}
                  </Link>
                  <TagBox>{p.status.replaceAll("_", " ")}</TagBox>
                </li>
              ))}
              {projects.length === 0 && <li className="px-3 py-3 text-[12.5px] text-muted-foreground">No projects yet.</li>}
            </ul>
            <div className="border-t border-border px-3 py-1.5">
              <Link href={`/content?channel=${channel.id}`} className="font-mono text-[9.5px] uppercase tracking-wider text-ink hover:underline">
                open library <ArrowUpRight className="inline size-2.5" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
