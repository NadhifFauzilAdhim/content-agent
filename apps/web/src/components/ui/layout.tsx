import * as React from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Page structure per the design system:
 * breadcrumbs → editorial H1 → description → double rule → content.
 */
export function PageHeader({
  eyebrow,
  title,
  italic,
  description,
  actions,
  meta,
  breadcrumbs,
  children,
  className,
}: {
  eyebrow?: string;
  title: string;
  italic?: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  meta?: React.ReactNode;
  breadcrumbs?: { label: string; href?: string }[];
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("pt-6 md:pt-8", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          {breadcrumbs?.map((crumb, i) => (
            <React.Fragment key={`${crumb.label}-${i}`}>
              {i > 0 && <ChevronRight className="size-2.5 text-subtle" />}
              {crumb.href ? (
                <Link href={crumb.href} className="hover:text-ink hover:underline underline-offset-2">
                  {crumb.label}
                </Link>
              ) : (
                <span className="text-ink">{crumb.label}</span>
              )}
            </React.Fragment>
          ))}
          {!breadcrumbs && eyebrow && <span className="text-ink">{eyebrow}</span>}
        </nav>
        {meta && <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">{meta}</div>}
      </div>

      <div className="mt-4 flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div className="max-w-4xl">
          <h1 className="editorial-title text-[40px] leading-[0.95] sm:text-[52px] lg:text-[60px]">
            {title}
            {italic && <em className="ml-2 italic text-muted-foreground">{italic}</em>}
          </h1>
          {description && (
            <p className="mt-3 max-w-[68ch] text-[13.5px] leading-relaxed text-muted-foreground md:text-[14px]">
              {description}
            </p>
          )}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>

      <div className="mt-6" aria-hidden>
        <div className="border-t border-ink" />
        <div className="mt-[5px] border-t border-ink" />
      </div>
      {children}
    </header>
  );
}

export function SectionTitle({
  title,
  index,
  caption,
  actions,
  className,
  as = "h2",
}: {
  title: React.ReactNode;
  index?: string;
  caption?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  as?: "h2" | "h3";
}) {
  const Tag = as;
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-3 pb-2.5", className)}>
      <div className="flex items-baseline gap-3">
        {index && <span className="mono-label mb-1 text-subtle">{index}</span>}
        <Tag className="font-serif text-[22px] leading-none tracking-[-0.01em] text-ink">{title}</Tag>
        {caption && (
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground max-sm:hidden">
            {caption}
          </span>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Section ruled by a black hairline. No card chrome. */
export function Section({
  children,
  className,
  bleed = false,
  id,
}: {
  children: React.ReactNode;
  className?: string;
  bleed?: boolean;
  id?: string;
}) {
  return (
    <section id={id} className={cn("mt-8 border-t border-ink", className)}>
      <div className={cn(!bleed && "pt-4")}>{children}</div>
    </section>
  );
}

/** Framed panel — used only for interactive or selected regions. */
export function Panel({
  children,
  className,
  selected = false,
}: {
  children: React.ReactNode;
  className?: string;
  selected?: boolean;
}) {
  return (
    <div
      className={cn(
        "border bg-white",
        selected ? "border-ink shadow-[3px_3px_0_0_var(--accent)]" : "border-border",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center border border-border bg-white px-1 font-mono text-[10px] text-muted-foreground">
      {children}
    </kbd>
  );
}
