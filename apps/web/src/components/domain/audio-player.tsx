"use client";

import { useId, useState } from "react";
import { Check, Copy, Download } from "lucide-react";

import { buttonStyles } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Native audio player restyled to the design system. The browser's `audio` element is used (rather
 * than a custom transport) so scrubbing, keyboard access and screen-reader semantics come for free.
 */
export function AudioPlayer({
  src,
  label,
  caption,
  className,
}: {
  src?: string;
  label?: string;
  caption?: string;
  className?: string;
}) {
  if (!src) {
    return (
      <div
        className={cn(
          "flex h-12 items-center gap-3 border border-dashed border-border bg-paper px-3 font-mono text-[10px] uppercase tracking-[0.14em] text-subtle",
          className,
        )}
      >
        <span className="size-1.5 bg-border" />
        no audio yet
      </div>
    );
  }
  return (
    <div className={cn("border border-ink bg-white", className)}>
      {label && (
        <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink">{label}</span>
          {caption && (
            <span className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-subtle">{caption}</span>
          )}
        </div>
      )}
      <audio controls preload="metadata" src={src} className="audio-native w-full px-2 py-1.5" />
    </div>
  );
}

/** Range control with a live value, label and optional bounds — used for voice settings. */
export function RangeField({
  label,
  value,
  min,
  max,
  step = 0.05,
  defaultValue,
  onChange,
  help,
  disabled,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  defaultValue?: number;
  onChange: (v: number) => void;
  help?: string | null;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-1", disabled && "opacity-40")}>
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="mono-label text-ink">
          {label}
        </label>
        <span className="flex items-center gap-2 font-mono text-[11px] text-ink">
          {value.toFixed(2)}
          {defaultValue !== undefined && Math.abs(value - defaultValue) > 1e-6 && (
            <button
              type="button"
              onClick={() => onChange(defaultValue)}
              className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground underline underline-offset-2 hover:text-ink"
            >
              reset
            </button>
          )}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="range-native h-4 w-full"
      />
      {help && <p className="text-[11px] leading-snug text-muted-foreground">{help}</p>}
    </div>
  );
}

export function CopyButton({ value, label = "copy" }: { value: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className={buttonStyles("ghost", "xs")}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setDone(true);
          setTimeout(() => setDone(false), 1600);
        } catch {
          /* clipboard unavailable (insecure context) — the field remains selectable */
        }
      }}
    >
      {done ? <Check className="!size-2.5" /> : <Copy className="!size-2.5" />} {done ? "copied" : label}
    </button>
  );
}

export function DownloadLink({ href, filename }: { href: string; filename: string }) {
  return (
    <a href={href} download={filename} className={buttonStyles("outline", "xs")}>
      <Download className="!size-2.5" /> download
    </a>
  );
}
