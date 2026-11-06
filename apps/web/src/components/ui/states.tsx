import Link from "next/link";
import { AlertTriangle, ArrowUpRight, Inbox, PlugZap, RotateCw } from "lucide-react";

import { cn } from "@/lib/utils";
import { buttonStyles } from "./button";

export function EmptyState({
  title,
  description,
  action,
  icon,
  className,
}: {
  title: string;
  description: string;
  action?: { label: string; href: string } | { label: string; onClick?: () => void };
  icon?: "inbox" | "alert";
  className?: string;
}) {
  const Icon = icon === "alert" ? AlertTriangle : Inbox;
  return (
    <div
      className={cn(
        "flex flex-col items-start gap-3 border border-dashed border-border bg-paper px-6 py-10",
        className,
      )}
    >
      <Icon className="size-4 text-muted-foreground" strokeWidth={1.5} />
      <div>
        <p className="font-serif text-[20px] leading-none text-ink">{title}</p>
        <p className="mt-2 max-w-[52ch] text-[13px] leading-relaxed text-muted-foreground">{description}</p>
      </div>
      {action && "href" in action ? (
        <Link href={action.href} className={buttonStyles("secondary", "sm")}>
          {action.label} <ArrowUpRight className="!size-3" />
        </Link>
      ) : action ? (
        <button type="button" onClick={action.onClick} className={buttonStyles("secondary", "sm")}>
          {action.label}
        </button>
      ) : null}
    </div>
  );
}

/**
 * Explicit setup state — rendered when an integration is genuinely not configured.
 * Never replaced by fabricated operational data.
 */
export function SetupState({
  title,
  description,
  steps,
  action,
  className,
}: {
  title: string;
  description: string;
  steps?: { label: string; done?: boolean }[];
  action?: { label: string; href: string };
  className?: string;
}) {
  return (
    <div className={cn("border border-ink bg-white", className)}>
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2">
        <span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink">
          <PlugZap className="size-3" /> not configured
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-subtle">setup required</span>
      </div>
      <div className="px-4 py-5">
        <p className="font-serif text-[22px] leading-tight text-ink">{title}</p>
        <p className="mt-2 max-w-[60ch] text-[13px] leading-relaxed text-muted-foreground">{description}</p>
        {steps && (
          <ol className="mt-4 space-y-1.5 border-t border-border pt-3">
            {steps.map((step, i) => (
              <li key={step.label} className="flex items-baseline gap-3 text-[12.5px]">
                <span className="w-6 shrink-0 font-mono text-[10px] text-subtle">{String(i + 1).padStart(2, "0")}</span>
                <span className={cn(step.done ? "text-muted-foreground line-through" : "text-ink")}>{step.label}</span>
              </li>
            ))}
          </ol>
        )}
        {action && (
          <Link href={action.href} className={buttonStyles("primary", "sm", "mt-5")}>
            {action.label} <ArrowUpRight className="!size-3" />
          </Link>
        )}
      </div>
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  retryLabel = "Retry",
}: {
  title?: string;
  message: string;
  retryLabel?: string;
}) {
  return (
    <div className="flex items-start gap-3 border border-danger bg-[#FBEBEA] px-4 py-3">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" strokeWidth={1.6} />
      <div className="flex-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-danger">{title}</p>
        <p className="mt-1 text-[13px] text-ink">{message}</p>
      </div>
      <a
        href=""
        className="mt-0.5 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider text-ink hover:underline"
        onClick={(e) => e.preventDefault()}
      >
        <RotateCw className="size-3" /> {retryLabel}
      </a>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse bg-muted", className)} />;
}

export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-0">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 border-b border-border py-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className={cn("h-3.5", c === 0 ? "w-1/3" : "w-1/6")} />
          ))}
        </div>
      ))}
    </div>
  );
}
