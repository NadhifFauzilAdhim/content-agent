import * as React from "react";

import { cn } from "@/lib/utils";

const base =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-sans text-[13px] font-medium " +
  "transition-colors duration-150 disabled:pointer-events-none disabled:opacity-40 " +
  "focus-visible:outline-1 focus-visible:outline-ink focus-visible:outline-offset-2 " +
  "[&_svg]:size-3.5 [&_svg]:shrink-0 select-none";

const variants = {
  primary:
    "bg-ink text-white border border-ink hover:bg-white hover:text-ink active:bg-accent active:text-ink active:border-ink",
  secondary:
    "bg-white text-ink border border-ink hover:bg-ink hover:text-white",
  accent:
    "bg-accent text-ink border border-ink hover:bg-ink hover:text-accent",
  ghost: "text-ink hover:bg-muted border border-transparent hover:border-border",
  outline: "border border-border bg-white text-ink hover:border-ink hover:bg-muted",
  danger: "bg-danger text-white border border-danger hover:bg-white hover:text-danger",
  link: "text-ink underline underline-offset-4 decoration-border hover:decoration-ink p-0 h-auto",
} as const;

const sizes = {
  xs: "h-6 px-2 text-[11px]",
  sm: "h-7 px-2.5 text-[12px]",
  md: "h-8 px-3",
  lg: "h-10 px-4",
  icon: "size-7 p-0",
} as const;

export function buttonStyles(
  variant: keyof typeof variants = "primary",
  size: keyof typeof sizes = "md",
  className?: string,
) {
  return cn(base, variants[variant], sizes[size], className);
}

export function Button({
  className,
  variant = "primary",
  size = "md",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
}) {
  return <button className={cn(base, variants[variant], sizes[size], className)} {...props} />;
}
