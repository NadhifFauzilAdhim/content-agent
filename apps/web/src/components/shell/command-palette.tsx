"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  AudioLines,
  Bot,
  Boxes,
  CheckSquare,
  Coins,
  CornerDownLeft,
  LayoutDashboard,
  Radio,
  Search,
  Settings,
  TvMinimalPlay,
  Workflow,
} from "lucide-react";

import { cn } from "@/lib/utils";

type PaletteItem = {
  label: string;
  description: string;
  href: string;
  group: "navigate" | "action";
  icon: React.ElementType;
  keywords?: string;
};

const NAV: PaletteItem[] = [
  { label: "Overview", description: "Operational dashboard", href: "/", group: "navigate", icon: LayoutDashboard },
  { label: "Workflows", description: "Production pipeline monitor", href: "/workflows", group: "navigate", icon: Workflow },
  { label: "Approvals", description: "Human review queue", href: "/approvals", group: "navigate", icon: CheckSquare },
  { label: "Content", description: "Storyboards, renders, metadata", href: "/content", group: "navigate", icon: TvMinimalPlay },
  { label: "Channels", description: "Channels, contexts, schedules", href: "/channels", group: "navigate", icon: Radio },
  { label: "Agents", description: "Agent registry and configuration", href: "/agents", group: "navigate", icon: Bot },
  { label: "Providers", description: "LLM, TTS, image and YouTube providers", href: "/providers", group: "navigate", icon: Boxes },
  { label: "Audio Studio", description: "Generate and compare narration", href: "/studio/audio", group: "navigate", icon: AudioLines },
  { label: "Costs", description: "Spending, budgets and ledger", href: "/costs", group: "navigate", icon: Coins },
  { label: "Settings", description: "Workspace, team, security", href: "/settings", group: "navigate", icon: Settings },
];

export const SHORTCUTS = [
  { keys: ["ctrl", "k"], label: "Command palette" },
  { keys: ["g", "o"], label: "Go to overview" },
  { keys: ["g", "w"], label: "Go to workflows" },
  { keys: ["g", "a"], label: "Go to approvals" },
  { keys: ["g", "c"], label: "Go to content" },
  { keys: ["g", "n"], label: "Go to channels" },
  { keys: ["g", "p"], label: "Go to providers" },
  { keys: ["g", "u"], label: "Go to audio studio" },
  { keys: ["?"], label: "Keyboard shortcuts" },
  { keys: ["esc"], label: "Close overlays" },
];

const GOTO: Record<string, string> = {
  o: "/",
  w: "/workflows",
  a: "/approvals",
  c: "/content",
  n: "/channels",
  g: "/agents",
  p: "/providers",
  u: "/studio/audio",
  $: "/costs",
  s: "/settings",
};

export function CommandPalette({
  open,
  setOpen: setOpenRaw,
  extra,
}: {
  open: boolean;
  setOpen: (v: boolean) => void;
  extra: PaletteItem[];
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const [showKeys, setShowKeys] = useState(false);

  // single entry point: reset the search whenever the palette is opened
  const setOpen = useCallback(
    (openNext: boolean) => {
      if (openNext) {
        setQuery("");
        setCursor(0);
      }
      setOpenRaw(openNext);
    },
    [setOpenRaw],
  );

  const items = useMemo(() => {
    const all = [...NAV, ...extra];
    const q = query.trim().toLowerCase();
    if (!q) return all;
    return all.filter((i) =>
      `${i.label} ${i.description} ${i.keywords ?? ""}`.toLowerCase().includes(q),
    );
  }, [query, extra]);

  // global keyboard handling
  useEffect(() => {
    let gPressed = false;
    let gTimer: ReturnType<typeof setTimeout> | undefined;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!open);
        return;
      }
      if (e.key === "Escape") {
        setOpen(false);
        setShowKeys(false);
        return;
      }
      if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "?") {
        setShowKeys(true);
        return;
      }
      if (gPressed) {
        gPressed = false;
        if (gTimer) clearTimeout(gTimer);
        const dest = GOTO[e.key.toLowerCase()];
        if (dest) {
          e.preventDefault();
          router.push(dest);
        }
        return;
      }
      if (e.key.toLowerCase() === "g") {
        gPressed = true;
        gTimer = setTimeout(() => (gPressed = false), 900);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (gTimer) clearTimeout(gTimer);
    };
  }, [open, setOpen, router]);

  // Reset the query when opening. The reset happens in the open handler (not an effect) so it
  // cannot cascade renders; only focus (a DOM side effect) is applied on mount of the panel.
  useEffect(() => {
    if (!open) return;
    const id = setTimeout(() => inputRef.current?.focus(), 10);
    return () => clearTimeout(id);
  }, [open]);

  const go = useCallback(
    (item: PaletteItem) => {
      setOpen(false);
      router.push(item.href);
    },
    [router, setOpen],
  );

  if (!open && !showKeys) return null;

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-[70] flex items-start justify-center bg-ink/25 px-4 pt-[12vh] animate-fade-in" onMouseDown={() => setOpen(false)}>
          <div
            className="w-full max-w-[560px] border border-ink bg-white shadow-[4px_4px_0_0_#111] animate-slide-up"
            onMouseDown={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
          >
            <div className="flex items-center gap-2 border-b border-ink px-3 py-2.5">

              <Search className="size-4 text-muted-foreground" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setCursor(0);
                }}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") {
                    e.preventDefault();
                    setCursor((c) => Math.min(c + 1, items.length - 1));
                  } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    setCursor((c) => Math.max(c - 1, 0));
                  } else if (e.key === "Enter" && items[cursor]) {
                    e.preventDefault();
                    go(items[cursor]);
                  }
                }}
                placeholder="Jump to a page or channel…"
                className="flex-1 bg-transparent text-[14px] outline-none placeholder:text-subtle"
              />
              <kbd className="border border-border px-1 font-mono text-[9.5px] uppercase text-muted-foreground">esc</kbd>
            </div>
            <div className="scroll-thin max-h-[46vh] overflow-y-auto py-1">
              {items.length === 0 && (
                <p className="px-3 py-6 text-center font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                  no matches for “{query}”
                </p>
              )}
              {items.map((item, i) => (
                <button
                  key={`${item.href}-${item.label}`}
                  onMouseEnter={() => setCursor(i)}
                  onClick={() => go(item)}
                  className={cn(
                    "flex w-full items-center gap-3 px-3 py-2 text-left transition-colors",
                    cursor === i ? "bg-ink text-white" : "hover:bg-muted",
                  )}
                >
                  <item.icon className={cn("size-3.5 shrink-0", cursor === i ? "text-accent" : "text-muted-foreground")} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px]">{item.label}</span>
                    <span className={cn("block truncate font-mono text-[10px] uppercase tracking-wider", cursor === i ? "text-white/60" : "text-muted-foreground")}>
                      {item.description}
                    </span>
                  </span>
                  <span className={cn("font-mono text-[9.5px] uppercase tracking-wider", cursor === i ? "text-white/50" : "text-subtle")}>
                    {item.group}
                  </span>
                  {cursor === i && <CornerDownLeft className="size-3 text-accent" />}
                </button>
              ))}
            </div>
            <div className="flex items-center justify-between border-t border-border px-3 py-1.5 font-mono text-[9.5px] uppercase tracking-[0.12em] text-subtle">
              <span className="flex items-center gap-2">
                <span>↑↓ navigate</span>
                <span>↵ open</span>
              </span>
              <button onClick={() => { setOpen(false); setShowKeys(true); }} className="flex items-center gap-1 hover:text-ink">
                shortcuts <ArrowRight className="size-3" />
              </button>
            </div>
          </div>
        </div>
      )}

      {showKeys && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-ink/25 px-4 animate-fade-in" onMouseDown={() => setShowKeys(false)}>
          <div className="w-full max-w-[420px] border border-ink bg-white shadow-[4px_4px_0_0_#111]" onMouseDown={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-ink px-3 py-2">
              <span className="mono-label text-ink">Keyboard shortcuts</span>
              <button onClick={() => setShowKeys(false)} className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground hover:text-ink">close esc</button>
            </div>
            <ul className="divide-y divide-border">
              {SHORTCUTS.map((s) => (
                <li key={s.label} className="flex items-center justify-between px-3 py-2 text-[13px]">
                  <span>{s.label}</span>
                  <span className="flex gap-1">
                    {s.keys.map((k) => (
                      <kbd key={k} className="border border-border px-1.5 py-0.5 font-mono text-[10px] uppercase text-muted-foreground">{k}</kbd>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}

export type { PaletteItem };
