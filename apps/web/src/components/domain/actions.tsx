"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, Play, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { buttonStyles } from "@/components/ui/button";
import { cn } from "@/lib/utils";

async function call(path: string, method: "POST" | "PATCH" | "DELETE" | "PUT", body?: unknown) {
  const res = await fetch(`/api/proxy${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error?.message ?? `Request failed (${res.status})`);
  return data;
}

export { call };

export function RunProduction({
  channels,
  label = "run production",
  variant = "accent",
  disabled,
}: {
  channels: { id: string; name: string }[];
  label?: string;
  variant?: "accent" | "primary" | "secondary";
  disabled?: boolean;
}) {
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  async function start(channelId: string) {
    setPending(channelId);
    try {
      await call(`/workflows?channel_id=${channelId}&force_approval=true`, "POST");
      toast.success("Production queued", { description: "Awaiting human approval before publishing." });
      setOpen(false);
      router.refresh();
      router.push("/workflows");
    } catch (err) {
      toast.error("Could not start production", { description: (err as Error).message });
    } finally {
      setPending(null);
    }
  }

  if (channels.length === 0) {
    return (
      <Link href="/channels" className={buttonStyles("secondary", "md")}>
        <Play className="!size-3" /> create a channel first
      </Link>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        disabled={disabled || pending !== null}
        onClick={() => (channels.length === 1 ? start(channels[0].id) : setOpen((v) => !v))}
        className={buttonStyles(variant, "md")}
        aria-expanded={open}
      >
        {pending ? <Loader2 className="animate-spin !size-3" /> : <Play className="!size-3" />}
        {label}
      </button>
      {open && channels.length > 1 && (
        <div className="absolute right-0 z-30 mt-1 w-72 border border-ink bg-white p-1 shadow-[3px_3px_0_0_var(--accent)] animate-slide-up">
          <p className="mono-label px-2 py-1.5">choose channel</p>
          {channels.map((c) => (
            <button
              key={c.id}
              onClick={() => start(c.id)}
              disabled={pending !== null}
              className="flex w-full items-center justify-between px-2 py-1.5 text-left text-[12.5px] hover:bg-ink hover:text-white disabled:opacity-50"
            >
              {c.name}
              <span className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">run</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function RefreshButton({ label = "refresh", className }: { label?: string; className?: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  return (
    <button
      type="button"
      disabled={pending}
      onClick={() => {
        setPending(true);
        router.refresh();
        setTimeout(() => setPending(false), 800);
      }}
      className={cn(buttonStyles("secondary", "md"), className)}
    >
      <RefreshCw className={cn("!size-3", pending && "animate-spin")} /> {label}
    </button>
  );
}

export function ToastAction({
  path,
  method,
  body,
  success,
  children,
  confirm,
  variant = "secondary",
  disabled,
  className,
}: {
  path: string;
  method: "POST" | "PATCH" | "DELETE" | "PUT";
  body?: unknown;
  success: string;
  children: ReactNode;
  confirm?: string;
  variant?: "primary" | "secondary" | "accent" | "ghost" | "outline" | "danger" | "link";
  disabled?: boolean;
  className?: string;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  return (
    <button
      type="button"
      disabled={pending || disabled}
      className={cn(buttonStyles(variant, "md"), className)}
      onClick={async () => {
        if (confirm && !window.confirm(confirm)) return;
        setPending(true);
        try {
          await call(path, method, body);
          toast.success(success);
          router.refresh();
        } catch (err) {
          toast.error("Action failed", { description: (err as Error).message });
        } finally {
          setPending(false);
        }
      }}
    >
      {pending && <Loader2 className="animate-spin !size-3" />}
      {children}
    </button>
  );
}
