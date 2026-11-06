import Link from "next/link";
import { ArrowUpRight, Plus } from "lucide-react";

import { resources } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import type { Channel } from "@/lib/types";
import { RefreshButton, RunProduction } from "@/components/domain/actions";
import { buttonStyles } from "@/components/ui/button";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { EmptyState } from "@/components/ui/states";
import { StatusChip, TagBox } from "@/components/ui/status";
import { NewChannelForm } from "./new-channel";

export const metadata = { title: "Channels" };

function ChannelCard({ channel }: { channel: Channel }) {
  return (
    <li className="border border-border bg-white transition-colors hover:border-ink">
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="size-2.5 shrink-0" style={{ background: channel.accent_color }} aria-hidden />
            <Link href={`/channels/${channel.id}`} className="truncate font-serif text-[24px] leading-none hover:underline underline-offset-4">
              {channel.name}
            </Link>
          </div>
          <p className="mt-1.5 flex flex-wrap items-center gap-1.5 font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
            <TagBox>{channel.handle}</TagBox>
            <TagBox>{channel.niche}</TagBox>
            <TagBox>{channel.language}</TagBox>
            <TagBox>{channel.video_format}</TagBox>
          </p>
        </div>
        <StatusChip tone={channel.is_active ? "live" : "idle"} dot={false}>
          {channel.is_active ? "active" : "paused"}
        </StatusChip>
      </div>
      <div className="grid grid-cols-2 divide-x divide-border border-b border-border sm:grid-cols-4">
        {[
          { label: "produced", value: channel.production_count },
          { label: "published", value: channel.published_count },
          { label: "duration", value: `${Math.round((channel.settings?.target_duration_seconds ?? 0) / 60)}m` },
          { label: "approval", value: channel.settings?.approval_mode ?? "—" },
        ].map((s) => (
          <div key={s.label} className="px-3 py-2">
            <p className="mono-label">{s.label}</p>
            <p className="mono-value mt-1 text-[15px] leading-none">{s.value}</p>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
        <div className="flex min-w-0 flex-col">
          <span className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
            next run · {formatWhen(channel.next_run_at)}
          </span>
          <span className="font-mono text-[9.5px] uppercase tracking-wider text-subtle">
            {channel.youtube_channel_id ? (
              <>youtube · {channel.youtube_channel_title ?? channel.youtube_channel_id}</>
            ) : (
              <>youtube · not connected</>
            )}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {!channel.youtube_channel_id && (
            <Link href={`/channels/${channel.id}`} className={buttonStyles("outline", "xs")}>
              connect
            </Link>
          )}
          <Link href={`/channels/${channel.id}`} className={buttonStyles("secondary", "xs")}>
            manage <ArrowUpRight className="!size-2.5" />
          </Link>
        </div>
      </div>
    </li>
  );
}

export default async function ChannelsPage() {
  const [channels, integrations] = await Promise.all([resources.channels(), resources.integrations()]);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Channels" }]}
        title="Channels"
        italic="& contexts"
        description="A channel is a production context: niche, audience, language, visual identity, cast, quality policy and schedule. Every run is scoped to one channel, and channels are isolated."
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
            { label: "channels", value: String(channels.length), caption: "in workspace", accent: channels.length > 0 },
            { label: "active", value: String(channels.filter((c) => c.is_active).length), caption: "producing" },
            { label: "youtube", value: `${channels.filter((c) => c.youtube_channel_id).length}/${channels.length}`, caption: "connected" },
            { label: "produced", value: String(channels.reduce((s, c) => s + c.production_count, 0)), caption: "projects" },
            { label: "published", value: String(channels.reduce((s, c) => s + c.published_count, 0)), caption: "videos" },
            { label: "approved", value: String(channels.filter((c) => c.settings?.approval_mode === "always").length), caption: "human gate" },
            { label: "languages", value: String(new Set(channels.map((c) => c.language)).size), caption: "locales" },
            { label: "formats", value: String(new Set(channels.map((c) => c.video_format)).size), caption: "aspects" },
          ]}
        />
      </div>

      <Section>
        <SectionTitle
          title="Registered channels"
          index="01"
          caption="isolated contexts"
          actions={<span className="mono-label">{integrations.google_oauth_configured ? "oauth configured" : "oauth not configured"}</span>}
        />
        {channels.length === 0 ? (
          <EmptyState
            className="mt-3"
            title="No channels yet"
            description="Create the first channel to define its niche, audience, visual style, cast and publishing schedule."
          />
        ) : (
          <ul className="mt-1 grid gap-3 lg:grid-cols-2">
            {channels.map((c) => (
              <ChannelCard key={c.id} channel={c} />
            ))}
          </ul>
        )}
      </Section>

      <Section className="pb-8">
        <SectionTitle title="New channel" index="02" caption="context, audience, policy" actions={<Plus className="size-3.5 text-muted-foreground" />} />
        <NewChannelForm />
      </Section>
    </>
  );
}
