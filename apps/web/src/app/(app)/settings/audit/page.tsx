import { resources } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import { RefreshButton } from "@/components/domain/actions";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { EmptyState } from "@/components/ui/states";
import { TagBox } from "@/components/ui/status";

export const metadata = { title: "Audit log" };

export default async function AuditPage() {
  const audit = await resources.audit().catch(() => []);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "System" }, { label: "Audit log" }]}
        title="Audit"
        italic="trail"
        description="Authentication, credential changes, agent configuration, approvals and publishing decisions are recorded with actor and source address. Readable by workspace admins."
        actions={<RefreshButton />}
      />

      <Section className="mt-8">
        <SectionTitle title="Events" index="01" caption={`${audit.length} entries`} />
        {audit.length === 0 ? (
          <EmptyState
            title="No events visible"
            description="Either nothing has happened yet, or your role cannot read the workspace audit trail (admin required)."
          />
        ) : (
          <ul className="divide-y divide-border border-y border-border">
            {audit.map((a) => (
              <li key={a.id} className="grid gap-1 py-2 sm:grid-cols-[180px_1fr_auto] sm:items-center">
                <TagBox>{a.action}</TagBox>
                <span className="font-mono text-[10.5px] text-muted-foreground">
                  {a.target_type ? `${a.target_type}` : "—"}
                  {a.target_id ? ` · ${a.target_id.slice(0, 8)}` : ""}
                  {a.actor_id ? ` · actor ${a.actor_id.slice(0, 8)}` : ""}
                </span>
                <span className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">{formatWhen(a.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}
