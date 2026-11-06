"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import type { Channel, Session } from "@/lib/types";

import { CommandPalette, type PaletteItem } from "./command-palette";
import { Sidebar, type NavCounts } from "./sidebar";
import { Drawer, Topbar } from "./topbar";

export function AppShell({
  session,
  counts,
  channels,
  children,
}: {
  session: Session;
  counts: NavCounts;
  channels: Pick<Channel, "id" | "name" | "handle" | "is_active">[];
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const channelItems: PaletteItem[] = channels.map((c) => ({
    label: c.name,
    description: `channel · ${c.handle}`,
    href: `/channels/${c.id}`,
    group: "navigate" as const,
    icon: (props: React.ComponentProps<"svg">) => (
      <svg viewBox="0 0 16 16" {...props} aria-hidden>
        <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <circle cx="8" cy="8" r="2" fill="currentColor" />
      </svg>
    ),
    keywords: c.handle,
  }));

  async function logout() {
    await fetch("/api/session", { method: "DELETE" });
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="flex min-h-screen bg-white">
      <div className="sticky top-0 hidden h-screen lg:block">
        <Sidebar session={session} counts={counts} onLogout={logout} />
      </div>
      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        <Sidebar session={session} counts={counts} onLogout={logout} onNavigate={() => setDrawerOpen(false)} />
      </Drawer>
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          openPalette={() => setPaletteOpen(true)}
          onOpenDrawer={() => setDrawerOpen(true)}
          counts={counts}
        />
        <main className="flex-1 px-4 pb-16 md:px-7 lg:px-8">
          <div className="mx-auto w-full max-w-[1360px]">{children}</div>
        </main>
        <footer className="border-t border-border px-4 py-3 md:px-7 lg:px-8">
          <div className="mx-auto flex w-full max-w-[1360px] flex-wrap items-center justify-between gap-2 font-mono text-[9.5px] uppercase tracking-[0.14em] text-subtle">
            <span>factory · autonomous content studio</span>
            <span className="flex items-center gap-4">
              <span>scheduler · {counts.activeWorkflows > 0 ? "engaged" : "standby"}</span>
              <span>{new Date().getFullYear()}</span>
            </span>
          </div>
        </footer>
      </div>
      <CommandPalette open={paletteOpen} setOpen={setPaletteOpen} extra={channelItems} />
    </div>
  );
}
