import Link from "next/link";
import { ArrowRight, KeyRound } from "lucide-react";

import { resources, sessionToken, api } from "@/lib/api";
import type { TTSGeneration, TTSProviderRow, TTSUsage } from "@/lib/types";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { SetupState } from "@/components/ui/states";
import { formatDuration, formatUsd, relativeTime } from "@/lib/format";
import { AudioStudio } from "./audio-studio";
import { UsageBoard } from "./usage-board";

export const metadata = { title: "Audio studio" };

export default async function AudioStudioPage() {
  const token = await sessionToken();
  const [providers, history, usage, settings, session] = await Promise.all([
    resources.ttsProviders(),
    api<{ items: TTSGeneration[]; total: number }>("/tts/generations", { token, query: { limit: 12 } }).catch(
      () => ({ items: [], total: 0 }),
    ),
    api<TTSUsage>("/tts/usage", { token, query: { days: 30 } }).catch(() => null),
    api<{ workspace: Record<string, unknown> | null }>("/tts/settings", { token }).catch(() => ({
      workspace: null,
    })),
    resources.session(),
  ]);
  const canEdit = ["owner", "admin", "editor"].includes(session.workspace.role);
  const configured = providers.filter((p) => !p.mock && p.has_credential && p.enabled);
  const mocks = providers.filter((p) => p.mock);
  const usageAvailable = (usage?.totals.generations ?? 0) > 0;

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Studio" }, { label: "Audio" }]}
        title="Audio"
        italic="studio"
        description="Generate narration without running a full production: pick a provider, model and voice, preview the result, and compare Cartesia against ElevenLabs on the same text. Everything here is a test generation — it never publishes and is labelled as such in history."
        actions={
          <Link href="/providers" className="inline-flex h-8 items-center gap-2 border border-border bg-white px-3 text-[13px] hover:border-ink">
            <KeyRound className="size-3.5" /> manage keys
          </Link>
        }
      />

      {configured.length === 0 && mocks.length === 0 ? (
        <div className="mt-6">
          <SetupState
            title="No text-to-speech provider is configured"
            description="Audio Studio needs a Cartesia or ElevenLabs API key. Add it under Providers → Text to speech; the browser never sees the key."
            steps={[
              { label: "Create an API key at play.cartesia.ai/keys or elevenlabs.io" },
              { label: "Providers → Text to speech → Add key (admins only)" },
              { label: "Run test connection, then return here" },
            ]}
            action={{ label: "Open providers", href: "/providers" }}
          />
        </div>
      ) : configured.length === 0 ? (
        <div className="mt-6">
          <SetupState
            title="Listening to real voices needs an API key"
            description="Only the mock adapter is enabled: it generates a quiet tone with the correct duration for testing the interface and the production pipeline. Add a Cartesia or ElevenLabs key to generate real narration — no restart required."
            steps={[
              { label: "Create an API key at play.cartesia.ai/keys or elevenlabs.io" },
              { label: "Providers → Text to speech → add key, then test connection" },
              { label: "Return here; models and voices load automatically" },
            ]}
            action={{ label: "Open providers", href: "/providers" }}
          />
        </div>
      ) : (
        <div className="mt-6">
          <MetricStrip
            metrics={[
              { label: "providers", value: String(configured.length), caption: "with keys", accent: true },
              { label: "generations", value: String(usage?.totals.generations ?? 0), caption: "30 days" },
              {
                label: "audio",
                value: usage?.totals.audio_seconds ? formatDuration(usage.totals.audio_seconds) : "—",
                caption: "generated",
              },
              {
                label: "est. spend",
                value: usage?.totals.estimated_cost_usd ? formatUsd(usage.totals.estimated_cost_usd, 3) : "—",
                caption: "list price",
              },
              {
                label: "latency",
                value: usage?.totals.avg_latency_ms ? `${(usage.totals.avg_latency_ms / 1000).toFixed(1)}s` : "—",
                caption: "mean",
              },
              {
                label: "failed",
                value: String(usage?.totals.failed ?? 0),
                caption: "generations",
                accent: (usage?.totals.failed ?? 0) > 0,
              },
            ]}
          />
        </div>
      )}

      <Section>
        <SectionTitle title="Synthesise" index="01" caption="single voice · compare · dialogue" />
        {configured.length === 0 && mocks.length > 0 && (
          <p className="mb-3 border border-warning bg-[#FDF4DE] px-3 py-2 text-[12px] leading-relaxed text-[#8A6412]">
            Only the mock adapter is enabled. It produces a quiet test tone with the right duration —
            useful for checking the interface and pipeline, not for judging a voice. Add a Cartesia or
            ElevenLabs key under <a className="underline underline-offset-2" href="/providers">Providers</a> to hear real narration.
          </p>
        )}
        <AudioStudio
          providers={providers as TTSProviderRow[]}
          canEdit={canEdit}
          defaultProvider={(settings.workspace?.provider as string) || configured[0]?.slug || ""}
        />
      </Section>

      <Section>
        <SectionTitle
          title="History"
          index="02"
          caption="every generation, test and production"
          actions={
            history.items.length > 0 ? (
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                {history.total} total
              </span>
            ) : undefined
          }
        />
        {history.items.length === 0 ? (
          <p className="py-4 text-[13px] text-muted-foreground">
            Nothing generated yet. Your first preview will appear here with duration, latency and cost.
          </p>
        ) : (
          <div className="scroll-thin -mx-1 overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-[12.5px]">
              <thead>
                <tr className="border-b border-ink font-mono text-[9.5px] uppercase tracking-[0.14em] text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">when</th>
                  <th className="py-2 pr-3 font-medium">provider</th>
                  <th className="py-2 pr-3 font-medium">voice</th>
                  <th className="py-2 pr-3 font-medium">text</th>
                  <th className="py-2 pr-3 text-right font-medium">dur</th>
                  <th className="py-2 pr-3 text-right font-medium">latency</th>
                  <th className="py-2 pr-3 text-right font-medium">est.</th>
                  <th className="py-2 font-medium">status</th>
                </tr>
              </thead>
              <tbody>
                {history.items.map((g) => (
                  <tr key={g.id} className="border-b border-border">
                    <td className="py-2 pr-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                      {relativeTime(g.created_at)}
                    </td>
                    <td className="py-2 pr-3">
                      <span className="font-mono text-[11px] text-ink">{g.provider}</span>
                      <span className="ml-1.5 font-mono text-[9.5px] text-subtle">{g.model}</span>
                    </td>
                    <td className="max-w-[120px] truncate py-2 pr-3 font-mono text-[10px] text-muted-foreground" title={g.voice_id ?? ""}>
                      {g.voice_id ?? "—"}
                    </td>
                    <td className="max-w-[240px] truncate py-2 pr-3 text-muted-foreground" title={g.text}>
                      {g.text}
                    </td>
                    <td className="py-2 pr-3 text-right font-mono text-[11px]">
                      {g.duration_s ? `${g.duration_s.toFixed(1)}s` : "—"}
                    </td>
                    <td className="py-2 pr-3 text-right font-mono text-[11px] text-muted-foreground">
                      {(g.latency_ms / 1000).toFixed(1)}s
                    </td>
                    <td className="py-2 pr-3 text-right font-mono text-[11px]">{formatUsd(g.estimated_cost_usd, 4)}</td>
                    <td className="py-2">
                      <span
                        className={
                          g.status === "succeeded"
                            ? "font-mono text-[9.5px] uppercase tracking-wider text-[#4B6B0D]"
                            : g.status === "failed"
                              ? "font-mono text-[9.5px] uppercase tracking-wider text-danger"
                              : "font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground"
                        }
                        title={g.error_message ?? undefined}
                      >
                        {g.status}
                      </span>
                      {g.trigger !== "production" && g.status !== "failed" && (
                        <span className="ml-1.5 font-mono text-[9px] uppercase tracking-wider text-subtle">test</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section id="usage" className="pb-8">
        <SectionTitle title="Usage" index="03" caption="characters · duration · cost · latency" />
        {usageAvailable && usage ? (
          <UsageBoard usage={usage} />
        ) : (
          <p className="py-4 text-[13px] text-muted-foreground">
            No usage recorded in the last 30 days. Estimates use published list prices; actual billed
            amounts are recorded only when a provider reports them.
          </p>
        )}
        <p className="mt-4 flex items-center gap-2 text-[12px] text-muted-foreground">
          <ArrowRight className="size-3" /> Production narrations are attributed to their workflow and channel —
          see{" "}
          <Link href="/costs" className="text-ink underline underline-offset-4">
            Costs
          </Link>
          .
        </p>
      </Section>
    </>
  );
}
