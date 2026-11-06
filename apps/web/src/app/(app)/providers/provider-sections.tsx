"use client";

import { Fragment, useState } from "react";

import type { Provider } from "@/lib/types";
import { CredentialRow, CredentialToggle, ProviderActions } from "./provider-actions";
import { DataTable, TD, TH, THead, TR } from "@/components/ui/table";
import { StatusChip, TagBox } from "@/components/ui/status";
import { relativeTime } from "@/lib/format";

type ProviderRows = Provider[];

/**
 * Client wrapper for the provider tables: credentials expand into a full-width row, which needs
 * interactive state. The page itself stays a server component and passes data down.
 */
export function ProviderSections({
  groups,
  canManage,
}: {
  groups: { key: string; rows: ProviderRows }[];
  canManage: boolean;
}) {
  const [openKey, setOpenKey] = useState<string | null>(null);
  return (
    <div className="space-y-8">
      {groups.map((group) => (
        <div key={group.key}>
          {group.rows.length === 0 ? (
            <p className="py-4 text-[13px] text-muted-foreground">No adapter registered for this capability yet.</p>
          ) : (
            <DataTable minWidth="900px">
              <THead>
                <TH>provider</TH>
                <TH>adapter</TH>
                <TH>models</TH>
                <TH>credential</TH>
                <TH>health</TH>
                <TH align="right">actions</TH>
              </THead>
              <tbody>
                {group.rows.map((p) => (
                  <Fragment key={p.id}>
                    <TR className={!p.is_enabled ? "opacity-60" : undefined}>
                      <TD>
                        <span className="block text-[13px] font-medium">{p.name}</span>
                        <span className="mt-0.5 flex items-center gap-1.5">
                          <TagBox emphasis>{p.slug}</TagBox>
                          {p.is_mock && (
                            <StatusChip tone="idle" dot={false}>
                              mock
                            </StatusChip>
                          )}
                          {!p.is_enabled && (
                            <StatusChip tone="idle" dot={false}>
                              disabled
                            </StatusChip>
                          )}
                        </span>
                      </TD>
                      <TD mono className="text-muted-foreground">
                        {p.vendor}
                      </TD>
                      <TD>
                        <span className="flex max-w-[240px] flex-wrap gap-1">
                          {p.models.slice(0, 3).map((m) => (
                            <TagBox key={m.id}>{m.name ?? m.id}</TagBox>
                          ))}
                          {p.models.length > 3 && <TagBox>+{p.models.length - 3}</TagBox>}
                          {p.models.length === 0 && <span className="text-[12px] text-muted-foreground">—</span>}
                        </span>
                      </TD>
                      <TD mono>
                        {p.is_mock ? (
                          <span className="text-muted-foreground">not required</span>
                        ) : p.has_credential ? (
                          <span className="flex flex-col gap-0.5">
                            <span className="text-ink">{p.credential_fingerprint}</span>
                            <span className="font-mono text-[9px] uppercase tracking-wider text-subtle">
                              v{p.credential_version} ·{" "}
                              {p.credential_updated_at ? `set ${relativeTime(p.credential_updated_at)}` : "—"}
                            </span>
                          </span>
                        ) : (
                          <span className="text-[#8A6412]">
                            {p.credential_status === "disabled" ? "removed" : "no key"}
                          </span>
                        )}
                      </TD>
                      <TD>
                        <StatusChip
                          tone={
                            p.health === "ok"
                              ? "success"
                              : p.health === "error"
                                ? "danger"
                                : p.health === "degraded"
                                  ? "warning"
                                  : "idle"
                          }
                        >
                          {p.health}
                        </StatusChip>
                        <span
                          className="mt-0.5 block max-w-[180px] truncate font-mono text-[9.5px] uppercase tracking-wider text-subtle"
                          title={p.health_detail ?? undefined}
                        >
                          {p.health_detail
                            ? p.health_detail
                            : p.health_checked_at
                              ? `checked ${relativeTime(p.health_checked_at)}`
                              : "not tested"}
                        </span>
                      </TD>
                      <TD align="right">
                        <div className="flex flex-col items-end gap-1.5">
                          <ProviderActions provider={p} canManage={canManage} />
                          <CredentialToggle
                            provider={p}
                            open={openKey === p.id}
                            onToggle={() => setOpenKey(openKey === p.id ? null : p.id)}
                          />
                        </div>
                      </TD>
                    </TR>
                    {openKey === p.id && <CredentialRow provider={p} canManage={canManage} />}
                  </Fragment>
                ))}
              </tbody>
            </DataTable>
          )}
        </div>
      ))}
    </div>
  );
}
