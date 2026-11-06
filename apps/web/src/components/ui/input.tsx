import * as React from "react";

import { cn } from "@/lib/utils";

const inputBase =
  "flex w-full rounded-xs border border-border bg-white px-3 font-sans text-[13px] text-ink " +
  "placeholder:text-subtle transition-colors outline-none " +
  "hover:border-ink focus:border-ink focus:ring-1 focus:ring-ink focus:shadow-[0_0_0_3px_var(--accent)] " +
  "disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-60 " +
  "aria-[invalid=true]:border-danger";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input ref={ref} className={cn(inputBase, "h-8", className)} {...props} />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={cn(inputBase, "min-h-24 py-2 leading-relaxed", className)} {...props} />
));
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <div className="relative">
    <select
      ref={ref}
      className={cn(inputBase, "h-8 appearance-none pr-8 cursor-pointer", className)}
      {...props}
    >
      {children}
    </select>
    <svg
      aria-hidden
      viewBox="0 0 12 12"
      className="pointer-events-none absolute right-2.5 top-1/2 size-3 -translate-y-1/2 text-muted-foreground"
    >
      <path d="M2 4.5 6 8.5 10 4.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  </div>
));
Select.displayName = "Select";

export function Field({
  label,
  hint,
  error,
  children,
  className,
  htmlFor,
  action,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
  className?: string;
  htmlFor?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={htmlFor} className="mono-label text-ink">
          {label}
        </label>
        {action}
      </div>
      {children}
      {error ? (
        <p className="font-mono text-[10px] uppercase tracking-wider text-danger">{error}</p>
      ) : hint ? (
        <p className="text-[12px] leading-snug text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

export function Checkbox({
  label,
  description,
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label: string; description?: string }) {
  return (
    <label className={cn("group flex cursor-pointer items-start gap-2.5 text-[13px]", className)}>
      <span className="relative mt-px flex size-4 shrink-0 items-center justify-center border border-ink bg-white transition-colors group-hover:bg-muted">
        <input type="checkbox" className="peer absolute inset-0 cursor-pointer opacity-0" {...props} />
        <svg
          viewBox="0 0 12 12"
          aria-hidden
          className="size-3 text-ink opacity-0 transition-opacity peer-checked:opacity-100"
        >
          <path d="M2.5 6.2 5 8.7 9.7 3.6" fill="none" stroke="currentColor" strokeWidth="1.8" />
        </svg>
      </span>
      <span className="flex flex-col gap-0.5">
        <span className="leading-4 text-ink">{label}</span>
        {description && <span className="text-[12px] leading-snug text-muted-foreground">{description}</span>}
      </span>
    </label>
  );
}

export function Switch({
  checked,
  onCheckedChange,
  label,
  disabled,
}: {
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
  label?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative h-5 w-9 shrink-0 border border-ink transition-colors",
        checked ? "bg-accent" : "bg-white hover:bg-muted",
        disabled && "opacity-40",
      )}
    >
      <span
        className={cn(
          "absolute top-0 h-3.5 w-3.5 border border-ink bg-ink transition-all",
          checked ? "left-[18px] bg-ink" : "left-[2px]",
        )}
        style={{ top: 2, height: 14, width: 14 }}
      />
    </button>
  );
}
