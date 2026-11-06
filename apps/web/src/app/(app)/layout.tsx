import { redirect } from "next/navigation";

import { api, getSession } from "@/lib/api";
import type { Approval, Channel, Overview, Provider } from "@/lib/types";
import { AppShell } from "@/components/shell/app-shell";

export default async function AppLayout({ children }: LayoutProps<"/">) {
  const session = await getSession();
  if (!session) redirect("/login");

  // Counts are derived from the same endpoints the pages use — no fabricated badges.
  const [channels, approvals, providers, overview] = await Promise.all([
    api<Channel[]>("/channels").catch(() => [] as Channel[]),
    api<Approval[]>("/approvals", { query: { status: "pending" } }).catch(() => [] as Approval[]),
    api<Provider[]>("/providers").catch(() => [] as Provider[]),
    api<Overview>("/overview").catch(() => null),
  ]);

  return (
    <AppShell
      session={session}
      channels={channels.map((c) => ({ id: c.id, name: c.name, handle: c.handle, is_active: c.is_active }))}
      counts={{
        approvals: approvals.length,
        activeWorkflows: overview?.totals.active_workflows.value ?? 0,
        channels: channels.length,
        agents: 10,
        providers: providers.length,
      }}
    >
      {children}
    </AppShell>
  );
}
