import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { resources } from "@/lib/api";
import { formatUsd, relativeTime } from "@/lib/format";
import type { Agent } from "@/lib/types";
import { AgentConfigurator } from "./configurator";
import { RefreshButton } from "@/components/domain/actions";
import { buttonStyles } from "@/components/ui/button";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { StatusChip, TagBox } from "@/components/ui/status";

export const metadata = { title: "Agents" };

const PORT_HINT: Record<string, string> = {
  llm: "OpenAI · Gemini",
  tts: "Cartesia · ElevenLabs",
  image: "OpenAI · Gemini",
  video: "FFmpeg · Remotion",
  rules: "deterministic",
  youtube: "Data API v3",
};

function AgentRow({ agent, providers }: { agent: Agent; providers: Awaited<ReturnType<typeof resources.providers>> }) {
  return (
    <li className="grid gap-3 py-4 lg:grid-cols-[260px_minmax(0,1fr)_260px]">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-subtle">{agent.stage.toUpperCase()}</span>
          <StatusChip
            tone={agent.status === "active" ? "live" : agent.status === "unconfigured" ? "warning" : "idle"}
            dot={false}
          >
            {agent.status}
          </StatusChip>
        </div>
        <p className="mt-1 font-serif text-[22px] leading-none">{agent.name}</p>
        <p className="mt-1 font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">{agent.key}</p>
        <div className="mt-2 flex flex-wrap items-center gap-1">
          <TagBox emphasis>{agent.port}</TagBox>
          <TagBox>{PORT_HINT[agent.port] ?? agent.port}</TagBox>
        </div>
      </div>

      <div className="min-w-0">
        <p className="text-[12.5px] leading-relaxed text-muted-foreground">{agent.description}</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-wider">
          <span className="text-muted-foreground">
            provider <span className="text-ink">{agent.provider_name ?? "—"}</span>
          </span>
          <span className="text-muted-foreground">
            model <span className="text-ink normal-case tracking-normal">{agent.model || "—"}</span>
          </span>
          {agent.port === "llm" && (
            <span className="text-muted-foreground">temp <span className="text-ink">{agent.temperature}</span></span>
          )}
          {agent.system_prompt && <StatusChip tone="warning" dot={false}>custom prompt</StatusChip>}
        </div>
        <div className="mt-3">
          <AgentConfigurator agent={agent} providers={providers} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 lg:grid-cols-1 lg:border-l lg:border-border lg:pl-4">
        <div>
          <p className="mono-label">executions</p>
          <p className="mono-value text-[18px]">{agent.executions}</p>
        </div>
        <div>
          <p className="mono-label">success</p>
          <p className="mono-value text-[18px]">
            {agent.success_rate === null ? "—" : `${agent.success_rate}%`}
          </p>
          <div className="mt-1 h-[3px] w-full max-w-[120px] bg-muted" aria-hidden>
            <div className="h-[3px] bg-accent" style={{ width: `${agent.success_rate ?? 0}%` }} />
          </div>
        </div>
        <div className="flex gap-6 lg:gap-0 lg:justify-between">
          <span>
            <span className="mono-label block">avg time</span>
            <span className="mono-value text-[12px]">
              {agent.avg_duration_ms === null
                ? "—"
                : agent.avg_duration_ms < 1000
                  ? `${agent.avg_duration_ms}ms`
                  : `${(agent.avg_duration_ms / 1000).toFixed(1)}s`}
            </span>
          </span>
          <span>
            <span className="mono-label block">cost</span>
            <span className="mono-value text-[12px]">{formatUsd(agent.total_cost_usd, 3)}</span>
          </span>
          <span>
            <span className="mono-label block">last run</span>
            <span className="mono-value text-[12px]">{relativeTime(agent.last_run_at)}</span>
          </span>
        </div>
      </div>
    </li>
  );
}

export default async function AgentsPage() {
  const [agents, providers] = await Promise.all([resources.agents(), resources.providers()]);
  const active = agents.filter((a) => a.status === "active");
  const unconfigured = agents.filter((a) => a.status === "unconfigured");
  const totalExecutions = agents.reduce((s, a) => s + a.executions, 0);
  const weighted = agents.filter((a) => a.success_rate !== null && a.executions > 0);
  const weightedExec = weighted.reduce((s, a) => s + a.executions, 0);
  const success = weightedExec
    ? Math.round(weighted.reduce((s, a) => s + (a.success_rate ?? 0) * a.executions, 0) / weightedExec)
    : null;

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Agents" }]}
        title="Agent"
        italic="registry"
        description="Ten specialised agents share a common contract: typed input, validated structured output, retry policy, cost accounting and per-provider configuration. Business logic never depends on a specific vendor."
        actions={
          <>
            <RefreshButton />
            <Link href="/providers" className={buttonStyles("secondary", "md")}>
              providers <ArrowUpRight className="!size-3" />
            </Link>
          </>
        }
      />

      <div className="mt-6">
        <MetricStrip
          metrics={[
            { label: "registered", value: String(agents.length), caption: "code registry" },
            { label: "active", value: String(active.length), caption: "ready to run", accent: active.length > 0 },
            { label: "unconfigured", value: String(unconfigured.length), caption: "missing provider", accent: unconfigured.length > 0 },
            { label: "paused", value: String(agents.filter((a) => a.status === "paused").length), caption: "disabled" },
            { label: "executions", value: String(totalExecutions), caption: "30 days" },
            { label: "success", value: success === null ? "—" : `${success}%`, caption: "weighted" },
            { label: "cost", value: formatUsd(agents.reduce((s, a) => s + a.total_cost_usd, 0), 3), caption: "30 days" },
            { label: "providers", value: String(providers.length), caption: "configured" },
          ]}
        />
      </div>

      <Section>
        <SectionTitle
          title="Agents in execution order"
          index="01"
          caption="plan → publish"
          actions={<span className="mono-label">click configure to bind providers & prompts</span>}
        />
        <ol className="divide-y divide-border border-b border-border">
          {agents.map((a) => (
            <AgentRow key={a.id} agent={a} providers={providers} />
          ))}
        </ol>
      </Section>

      {unconfigured.length > 0 && (
        <Section className="pb-6">
          <SectionTitle title="Requirements" index="02" caption="agents waiting on a provider" />
          <ul className="grid gap-2 md:grid-cols-2">
            {unconfigured.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 border border-border bg-paper px-3 py-2">
                <span>
                  <span className="block text-[12.5px]">{a.name}</span>
                  <span className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
                    needs a {a.port.toUpperCase()} provider with a credential
                  </span>
                </span>
                <Link href="/providers" className={buttonStyles("outline", "xs")}>
                  add provider
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}
