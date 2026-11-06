import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function DataTable({
  children,
  className,
  minWidth,
}: {
  children: ReactNode;
  className?: string;
  minWidth?: string;
}) {
  return (
    <div className={cn("scroll-thin -mx-px overflow-x-auto", className)}>
      <table
        className="w-full border-collapse text-left"
        style={minWidth ? { minWidth } : undefined}
      >
        {children}
      </table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return (
    <thead>
      <tr className="border-y border-border">{children}</tr>
    </thead>
  );
}

export function TH({
  children,
  className,
  align = "left",
}: {
  children?: ReactNode;
  className?: string;
  align?: "left" | "right" | "center";
}) {
  return (
    <th
      scope="col"
      className={cn(
        "whitespace-nowrap px-2.5 py-2 font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function TR({
  children,
  className,
  href,
}: {
  children: ReactNode;
  className?: string;
  href?: string;
}) {
  const inner = (
    <tr
      className={cn(
        "group border-b border-border transition-colors hover:bg-muted/70",
        href && "cursor-pointer",
        className,
      )}
    >
      {children}
    </tr>
  );
  return inner;
}

export function TD({
  children,
  className,
  align = "left",
  mono,
}: {
  children?: ReactNode;
  className?: string;
  align?: "left" | "right" | "center";
  mono?: boolean;
}) {
  return (
    <td
      className={cn(
        "px-2.5 py-2.5 align-middle text-[13px] text-ink",
        mono && "font-mono text-[11.5px] tabular",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
    >
      {children}
    </td>
  );
}

export function RowLink({
  href,
  children,
  className,
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <a href={href} className={cn("block", className)}>
      {children}
    </a>
  );
}
