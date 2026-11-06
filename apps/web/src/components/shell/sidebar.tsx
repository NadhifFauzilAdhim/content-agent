"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  AudioLines,
  Bot,
  Boxes,
  ChartNoAxesCombined,
  ChevronsUpDown,
  CheckSquare,
  Coins,
  Factory,
  LayoutDashboard,
  LogOut,
  Radio,
  Settings,
  TerminalSquare,
  TvMinimalPlay,
  Workflow,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { Session } from "@/lib/types";
import { LiveDot } from "@/components/ui/status";

export type NavCounts = {
  approvals: number;
  activeWorkflows: number;
  channels: number;
  agents: number;
  providers: number;
};

const groups: {
  label: string;
  items: { label: string; href: string; icon: React.ElementType; countKey?: keyof NavCounts }[];
}[] = [
  {
    label: "Operate",
    items: [
      { label: "Overview", href: "/", icon: LayoutDashboard, countKey: "activeWorkflows" },
      { label: "Workflows", href: "/workflows", icon: Workflow, countKey: "activeWorkflows" },
      { label: "Approvals", href: "/approvals", icon: CheckSquare, countKey: "approvals" },
      { label: "Content", href: "/content", icon: TvMinimalPlay },
    ],
  },
  {
    label: "Studio",
    items: [
      { label: "Channels", href: "/channels", icon: Radio, countKey: "channels" },
      { label: "Agents", href: "/agents", icon: Bot, countKey: "agents" },
      { label: "Providers", href: "/providers", icon: Boxes, countKey: "providers" },
      { label: "Audio Studio", href: "/studio/audio", icon: AudioLines },
    ],
  },
  {
    label: "Insight",
    items: [
      { label: "Analytics", href: "/analytics", icon: ChartNoAxesCombined },
      { label: "Costs", href: "/costs", icon: Coins },
    ],
  },
  {
    label: "System",
    items: [
      { label: "Settings", href: "/settings", icon: Settings },
      { label: "Logs", href: "/settings/audit", icon: TerminalSquare },
    ],
  },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar({
  session,
  counts,
  onLogout,
  onNavigate,
}: {
  session: Session;
  counts: NavCounts;
  onLogout: () => void;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const role = session.workspace.role;
  return (
    <aside className="flex h-full max-h-screen w-[236px] shrink-0 flex-col overflow-hidden border-r border-border bg-white">
      {/* brand */}
      <div className="flex h-14 items-center justify-between gap-2 border-b border-border px-4">
        <Link href="/" onClick={onNavigate} className="flex items-center gap-2 group">
          <span className="grid size-4 place-items-center bg-ink text-accent" aria-hidden>
            <span className="size-1.5 bg-accent" />
          </span>
          <span className="text-[17px] font-semibold tracking-[-0.02em] text-ink">
            factory<span className="text-muted-foreground">/</span>ai
          </span>
        </Link>
        <span className="inline-flex h-5 items-center bg-accent px-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.08em] text-ink">
          live
        </span>
      </div>

      {/* workspace selector */}
      <div className="border-b border-border px-3 py-3">
        <p className="mono-label mb-2 px-1">Workspace</p>
        <button
          type="button"
          className="flex w-full items-center justify-between gap-2 border border-border px-2 py-1.5 text-left transition-colors hover:border-ink"
          aria-label="Active workspace"
        >
          <span className="flex min-w-0 items-center gap-2">
            <span className="grid size-5 shrink-0 place-items-center bg-ink font-mono text-[10px] text-white">
              {session.workspace.name.slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-[12.5px] leading-tight text-ink">{session.workspace.name}</span>
              <span className="block font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
                {role} · {session.workspace.slug}
              </span>
            </span>
          </span>
          <ChevronsUpDown className="size-3 shrink-0 text-muted-foreground" />
        </button>
      </div>

      <nav className="scroll-thin min-h-0 flex-1 overflow-y-auto px-3 pb-3 pt-2" aria-label="Primary">
        {groups.map((group) => (
          <div key={group.label} className="mb-3">
            <p className="mono-label px-1 py-1.5">{group.label}</p>
            <ul className="space-y-px">
              {group.items.map((item) => {
                const active = isActive(pathname, item.href);
                const count = item.countKey ? counts[item.countKey] : 0;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "group flex h-8 items-center gap-2.5 px-2 text-[13px] transition-colors",
                        active
                          ? "bg-ink text-white"
                          : "text-ink/85 hover:bg-muted hover:text-ink",
                      )}
                    >
                      <item.icon
                        className={cn("size-[15px] shrink-0", active ? "text-white" : "text-muted-foreground group-hover:text-ink")}
                        strokeWidth={1.6}
                      />
                      <span className="flex-1 truncate">{item.label}</span>
                      {item.countKey && count > 0 && (
                        <span
                          className={cn(
                            "inline-flex h-4 min-w-4 items-center justify-center px-1 font-mono text-[10px] leading-none",
                            active ? "bg-accent text-ink" : "bg-muted text-muted-foreground",
                          )}
                        >
                          {count}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-border px-3 py-2.5">
        <div className="flex items-center gap-2">
          <LiveDot />
          <div className="min-w-0 flex-1">
            <p className="text-[12px] font-medium text-ink">
              {counts.activeWorkflows > 0 ? "Factory working" : "Factory idle"}
            </p>
            <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {counts.activeWorkflows} active · {counts.approvals} to review
            </p>
          </div>
        </div>
      </div>

      <div className="border-t border-border px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span
            className="grid size-7 shrink-0 place-items-center border border-ink font-mono text-[11px] text-ink"
            style={{ background: session.user.avatar_color }}
          >
            {session.user.name.slice(0, 1).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[12.5px] leading-tight text-ink">{session.user.name}</p>
            <p className="truncate font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
              {session.user.email}
            </p>
          </div>
          <button
            type="button"
            onClick={onLogout}
            title="Sign out"
            aria-label="Sign out"
            className="grid size-7 shrink-0 place-items-center border border-transparent text-muted-foreground transition-colors hover:border-border hover:text-ink"
          >
            <LogOut className="size-3.5" />
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-border px-3 py-1.5 font-mono text-[9.5px] uppercase tracking-[0.14em] text-subtle">
        <span className="flex items-center gap-1.5">
          <Activity className="size-3" /> v0.1 · studio
        </span>
        <span className="flex items-center gap-1">
          <Factory className="size-3" /> api
        </span>
      </div>
    </aside>
  );
}
