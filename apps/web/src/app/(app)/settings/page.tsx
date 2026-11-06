import { api, resources, sessionToken } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import { RefreshButton } from "@/components/domain/actions";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { StatusChip } from "@/components/ui/status";
import { DataTable, TD, TH, THead, TR } from "@/components/ui/table";
import { ApiKeyManager, ChangePassword, InviteMember } from "./settings-forms";
import { VoiceDefaults, type VoiceSettingsState } from "./voice-defaults";

export const metadata = { title: "Settings" };

export default async function SettingsPage() {
  const token = await sessionToken();
  const [workspace, members, integrations, status, audit, keys, ttsSettings, ttsProviders] = await Promise.all([
    resources.workspace(),
    resources.members(),
    resources.integrations(),
    resources.systemStatus(),
    resources.audit().catch(() => []),
    resources.apiKeys().catch(() => []),
    api<{ workspace: VoiceSettingsState }>("/tts/settings", { token }).catch(() => ({ workspace: null })),
    resources.ttsProviders().catch(() => []),
  ]);
  const canManage = ["owner", "admin"].includes(workspace.role);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Settings" }]}
        title="Workspace"
        italic="& system"
        description="Tenancy, roles, credentials and runtime health. Actions on this page require the admin role except password changes."
        actions={<RefreshButton />}
      />

      <div className="mt-6">
        <MetricStrip
          metrics={[
            { label: "workspace", value: workspace.slug, caption: `${workspace.plan} plan` },
            { label: "your role", value: workspace.role, caption: "rbac", accent: true },
            { label: "members", value: String(members.length), caption: "with access" },
            { label: "environment", value: integrations.environment, caption: "api runtime" },
            { label: "storage", value: integrations.storage_backend, caption: "asset backend" },
            { label: "ffmpeg", value: integrations.ffmpeg_available ? "ready" : "missing", caption: "renderer" },
            { label: "scheduler", value: integrations.scheduler_enabled ? "on" : "off", caption: `${status.scheduler.active_schedules} schedules` },
          ]}
        />
      </div>

      <Section>
        <SectionTitle title="Runtime" index="01" caption="service health" />
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {status.services.map((s) => (
            <li key={s.name} className="flex items-center justify-between gap-3 border border-border px-3 py-2">
              <span className="min-w-0">
                <span className="block text-[12.5px] capitalize">{s.name}</span>
                <span className="block truncate font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">{s.detail}</span>
              </span>
              <StatusChip tone={s.status === "ok" ? "success" : s.status === "paused" ? "warning" : "idle"} dot={false}>{s.status}</StatusChip>
            </li>
          ))}
        </ul>
      </Section>

      <Section>
        <SectionTitle title="Team" index="02" caption="role-based access" />
        <DataTable minWidth="600px">
          <THead>
            <TH>member</TH>
            <TH>email</TH>
            <TH>role</TH>
            <TH align="right">last sign-in</TH>
          </THead>
          <tbody>
            {members.map((m) => (
              <TR key={m.id}>
                <TD className="text-[12.5px]">{m.name}</TD>
                <TD mono className="text-muted-foreground">{m.email}</TD>
                <TD><StatusChip tone={m.role === "owner" ? "live" : "idle"} dot={false}>{m.role}</StatusChip></TD>
                <TD align="right" mono className="text-muted-foreground">{formatWhen(m.last_login_at)}</TD>
              </TR>
            ))}
          </tbody>
        </DataTable>
        <div className="mt-4 border-t border-border pt-4">
          <InviteMember />
        </div>
      </Section>

      <Section>
        <SectionTitle title="Voice defaults" index="03" caption="text to speech · workspace scope" />
        <VoiceDefaults providers={ttsProviders} current={ttsSettings.workspace} canManage={canManage} />
      </Section>

      <Section>
        <SectionTitle title="Security" index="04" caption="credentials & machine access" />
        <div className="grid gap-8 lg:grid-cols-2">
          <div>
            <p className="mono-label mb-2 text-ink">your password</p>
            <ChangePassword />
            <p className="mono-label mb-2 mt-6 text-ink">api keys</p>
            <ApiKeyManager keys={keys} />
          </div>
          <div>
            <p className="mono-label mb-2 text-ink">audit log · latest 80</p>
            <div className="max-h-[340px] overflow-y-auto border border-border scroll-thin">
              <ul className="divide-y divide-border">
                {audit.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-2 px-2.5 py-1.5">
                    <span className="font-mono text-[10.5px]">{a.action}</span>
                    <span className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">{formatWhen(a.created_at)}</span>
                  </li>
                ))}
                {audit.length === 0 && <li className="px-2.5 py-3 text-[12px] text-muted-foreground">No audit entries visible for your role.</li>}
              </ul>
            </div>
          </div>
        </div>
      </Section>
    </>
  );
}
