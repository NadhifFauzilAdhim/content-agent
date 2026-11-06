"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Bell, Command, Menu, Search, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Session } from "@/lib/types";
import { LiveDot } from "@/components/ui/status";

export function Topbar({
  openPalette,
  onOpenDrawer,
  counts,
}: {
  openPalette: () => void;
  onOpenDrawer: () => void;
  counts: { approvals: number; activeWorkflows: number };
}) {
  const pathname = usePathname();
  const [clock, setClock] = useState<string>("");
  useEffect(() => {
    const tick = () =>
      setClock(
        new Intl.DateTimeFormat("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
          timeZoneName: undefined,
        }).format(new Date()),
      );
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const parts = pathname
    .split("/")
    .filter(Boolean)
    .map((p) => (UUID.test(p) ? `#${p.slice(0, 8)}` : p.replaceAll("-", " ")));
  const crumb = parts.length === 0 ? "overview" : parts.join(" / ");

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-white/95 px-4 backdrop-blur-sm md:px-5">
      <button
        type="button"
        onClick={onOpenDrawer}
        className="grid size-8 place-items-center border border-border lg:hidden"
        aria-label="Open navigation"
      >
        <Menu className="size-4" />
      </button>

      <div className="hidden min-w-0 items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground sm:flex">
        <span className="text-ink">factory</span>
        <span className="text-subtle">/</span>
        <span className="truncate">{crumb}</span>
      </div>

      <div className="flex flex-1 items-center justify-end gap-2">
        <button
          type="button"
          onClick={openPalette}
          className="group flex h-8 w-full max-w-[340px] items-center gap-2 border border-border bg-white px-2.5 text-left transition-colors hover:border-ink"
        >
          <Search className="size-3.5 text-muted-foreground" />
          <span className="flex-1 truncate text-[12.5px] text-subtle">
            Search channels, workflows, agents…
          </span>
          <span className="hidden items-center gap-0.5 sm:flex">
            <kbd className="border border-border px-1 font-mono text-[9.5px] text-muted-foreground">ctrl</kbd>
            <kbd className="border border-border px-1 font-mono text-[9.5px] text-muted-foreground">k</kbd>
          </span>
        </button>

        <div className="hidden items-center gap-4 md:flex">
          <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            <LiveDot tone={counts.activeWorkflows > 0 ? "live" : "idle"} />
            {counts.activeWorkflows > 0 ? "production" : "idle"}
          </span>
          <span className="font-mono text-[10px] tracking-[0.08em] text-muted-foreground tabular">{clock}</span>
        </div>

        <Link
          href="/approvals"
          className="relative grid size-8 place-items-center border border-border transition-colors hover:border-ink"
          aria-label={`${counts.approvals} pending approvals`}
        >
          <Bell className="size-3.5" />
          {counts.approvals > 0 && (
            <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center bg-accent px-0.5 font-mono text-[9.5px] text-ink border border-ink">
              {counts.approvals}
            </span>
          )}
        </Link>
        <button
          type="button"
          onClick={openPalette}
          className="hidden items-center gap-1.5 border border-border px-2 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:border-ink hover:text-ink sm:flex"
          title="Keyboard shortcuts (press ?)"
        >
          <Command className="size-3" /> ?
        </button>
      </div>
    </header>
  );
}

export function Drawer({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className={cn("fixed inset-0 z-50 lg:hidden", open ? "" : "pointer-events-none")}>
      <div
        className={cn("absolute inset-0 bg-ink/30 transition-opacity", open ? "opacity-100" : "opacity-0")}
        onClick={onClose}
        aria-hidden
      />
      <div
        className={cn(
          "absolute inset-y-0 left-0 transition-transform duration-200 ease-out",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute -right-10 top-3 grid size-8 place-items-center border border-ink bg-white"
          aria-label="Close navigation"
        >
          <X className="size-4" />
        </button>
        {children}
      </div>
    </div>
  );
}

export function UserChip({ session, onLogout }: { session: Session; onLogout: () => void }) {
  return (
    <button
      onClick={onLogout}
      className="flex items-center gap-2 border border-border px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground hover:border-ink hover:text-ink"
    >
      <span
        className="grid size-4 place-items-center text-ink"
        style={{ background: session.user.avatar_color }}
      >
        {session.user.name.slice(0, 1)}
      </span>
      sign out
    </button>
  );
}
