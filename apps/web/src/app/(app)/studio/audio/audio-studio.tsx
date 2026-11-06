"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRightLeft,
  Check,
  Download,
  Layers,
  Loader2,
  Play,
  RefreshCw,
  Sparkles,
  Square,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import type { TTSGeneration, TTSModel, TTSProviderRow, TTSVoice } from "@/lib/types";
import { audioUrl, previewUrl, studio, StudioError } from "@/lib/studio";
import { buttonStyles } from "@/components/ui/button";
import { Field, Select, Textarea } from "@/components/ui/input";
import { AudioPlayer, RangeField } from "@/components/domain/audio-player";
import { cn } from "@/lib/utils";

type Mode = "single" | "compare" | "dialogue";

type Selection = {
  provider: string;
  model?: string;
  voice?: string;
  outputFormat?: string;
  settings: Record<string, unknown>;
  language: string;
};

type Catalogue = {
  models: TTSModel[];
  voices: TTSVoice[];
  error: string | null;
  loading: boolean;
};

const EMPTY: Catalogue = { models: [], voices: [], error: null, loading: false };

/** Module-level cache: capability lists are static per provider for the lifetime of a session. */
const CATALOGUE: Record<string, Catalogue> = {};
const listeners = new Set<() => void>();

async function loadCatalogue(provider: string): Promise<void> {
  if (!provider || CATALOGUE[provider]?.loading) return;
  CATALOGUE[provider] = { ...(CATALOGUE[provider] ?? EMPTY), loading: true };
  listeners.forEach((fn) => fn());
  try {
    const [m, v] = await Promise.all([
      studio<{ models: Record<string, TTSModel[]>; errors: Record<string, string> }>(
        `models?provider=${provider}`,
      ),
      studio<{ voices: Record<string, TTSVoice[]>; errors: Record<string, string> }>(
        `voices?provider=${provider}`,
      ),
    ]);
    CATALOGUE[provider] = {
      models: m.models[provider] ?? [],
      voices: v.voices[provider] ?? [],
      error: m.errors[provider] ?? v.errors[provider] ?? null,
      loading: false,
    };
    } catch (err) {
      CATALOGUE[provider] = {
        models: [],
        voices: [],
        error: err instanceof StudioError ? err.message : (err as Error).message,
        loading: false,
      };
    }
  listeners.forEach((fn) => fn());
}

/** Subscribe to the catalogue store; fetch on first use and on explicit reload. */
function useCatalogue(provider: string): Catalogue & { reload: () => void } {
  const [, force] = useState(0);
  useEffect(() => {
    const rerender = () => force((n) => n + 1);
    listeners.add(rerender);
    void loadCatalogue(provider);
    return () => {
      listeners.delete(rerender);
    };
  }, [provider]);
  const catalogue = CATALOGUE[provider] ?? EMPTY;
  const reload = useCallback(() => {
    delete CATALOGUE[provider];
    void loadCatalogue(provider);
  }, [provider]);
  return { ...catalogue, reload };
}

/**
 * A selection is *intent* only: model / voice / format are optional overrides. The effective
 * values come from the catalogue defaults, so nothing has to be synchronised with effects.
 */
function resolveSide(side: Selection, catalogue: Catalogue, provider?: TTSProviderRow) {
  const models = catalogue.models;
  const model =
    models.find((m) => m.id === side.model) ??
    models.find((m) => m.id === provider?.default_model) ??
    models[0];
  const params = model?.params ?? [];
  const voices = catalogue.voices;
  const voice =
    voices.find((v) => v.voice_id === side.voice) ??
    voices.find((v) => v.voice_id === provider?.default_voice) ??
    voices[0];
  const formats = model?.output_formats ?? [];
  const format =
    formats.find((f) => f.id === side.outputFormat) ??
    formats.find((f) => f.id === provider?.default_output_format) ??
    formats[0];
  const settings = Object.fromEntries([
    ...params.map((p) => [p.key, p.default] as const),
    ...Object.entries(side.settings),
  ]);
  return { model, voice, format, params, settings, voices, models, formats };
}

const SAMPLE =
  "The lighthouse keeper woke before the gulls. She climbed the hundred and twelve steps " +
  "with a lantern in each hand, and by the time she reached the lamp room, the whole harbour " +
  "was the colour of pale tea. \u201cMorning,\u201d she told the sea. The sea, as usual, said nothing.";

const LANGUAGES = [
  ["en", "English"], ["es", "Spanish"], ["fr", "French"], ["de", "German"], ["it", "Italian"],
  ["pt", "Portuguese"], ["ja", "Japanese"], ["ko", "Korean"], ["zh", "Chinese"], ["hi", "Hindi"],
  ["ar", "Arabic"], ["nl", "Dutch"], ["pl", "Polish"], ["tr", "Turkish"], ["sv", "Swedish"],
  ["id", "Indonesian"], ["uk", "Ukrainian"], ["ta", "Tamil"],
];

type CompareSideResult = {
  ok: boolean;
  provider: string;
  model?: string | null;
  voice_id?: string | null;
  output_format?: string;
  duration_s?: number;
  latency_ms: number;
  estimated_cost_usd?: number;
  characters?: number;
  audio_url?: string;
  generation_id?: string;
  warnings?: string[];
  error?: string;
  error_code?: string;
};

type CompareResult = {
  left: CompareSideResult;
  right: CompareSideResult;
  verdict: {
    winner: "left" | "right" | null;
    reason: string;
    cheaper?: "left" | "right" | "tie";
    faster?: "left" | "right" | "tie";
    cost_delta_usd?: number;
    latency_delta_ms?: number;
  };
};

type GenerationRequest = {
  kind: "single" | "dialogue" | "compare";
  path: string;
  body: Record<string, unknown>;
};

export function AudioStudio({
  providers,
  canEdit,
  defaultProvider,
}: {
  providers: TTSProviderRow[];
  canEdit: boolean;
  defaultProvider: string;
}) {
  const usable = providers.filter((p) => p.usable);
  const first = defaultProvider || usable[0]?.slug || "";
  const second = providers.find((p) => !p.mock && p.slug !== first)?.slug ?? usable[1]?.slug ?? first;

  const [mode, setMode] = useState<Mode>("single");
  const [left, setLeft] = useState<Selection>({ provider: first, settings: {}, language: "en" });
  const [right, setRight] = useState<Selection>({ provider: second, settings: {}, language: "en" });
  const [text, setText] = useState(SAMPLE);
  const [language, setLanguage] = useState("en");
  const [dialogue, setDialogue] = useState([
    { speaker: "Narrator", text: "Once, the river ran backwards for a whole afternoon.", voice_id: "" },
    { speaker: "Child", text: "But rivers can't run backwards!", voice_id: "" },
    { speaker: "Narrator", text: "This one could. And everyone came out to watch it.", voice_id: "" },
  ]);
  const [result, setResult] = useState<TTSGeneration | null>(null);
  const [comparison, setComparison] = useState<CompareResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [request, setRequest] = useState<GenerationRequest | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!busy) return;
    const origin = performance.now();
    const timer = setInterval(() => setElapsed((performance.now() - origin) / 1000), 250);
    return () => clearInterval(timer);
  }, [busy]);

  // The request lives in state and is executed here: the event handler stays pure (React
  // Compiler safety) and unmounting aborts the in-flight provider call.
  useEffect(() => {
    if (!request) return;
    const controller = new AbortController();
    abort.current = controller;
    let cancelled = false;

    (async () => {
      try {
        if (request.kind === "compare") {
          const data = await studio<CompareResult>("compare", {
            method: "POST",
            body: request.body,
            signal: controller.signal,
          });
          if (cancelled) return;
          setComparison(data);
          const ok = [data.left, data.right].filter((d) => d.ok).length;
          if (ok === 2) toast.success("Comparison ready", { description: "Listen, then keep the better voice." });
          else if (ok === 1) toast.warning("One side failed", { description: (data.left.ok ? data.right : data.left).error });
          else toast.error("Both sides failed", { description: data.left.error ?? data.right.error });
        } else {
          const data = await studio<TTSGeneration>(request.path, {
            method: "POST",
            body: request.body,
            signal: controller.signal,
          });
          if (cancelled) return;
          setResult(data);
          toast.success(request.kind === "dialogue" ? "Dialogue generated" : "Audio generated", {
            description: `${data.duration_s.toFixed(1)}s · ${data.provider} · ${data.chunk_count > 1 ? `${data.chunk_count} chunks · ` : ""}${(data.latency_ms / 1000).toFixed(1)}s`,
          });
        }
      } catch (err) {
        if (cancelled) return;
        if ((err as Error).name === "AbortError") {
          toast.info("Cancelled", { description: "The request was aborted before audio was stored." });
        } else {
          const message = err instanceof StudioError ? err.message : (err as Error).message;
          setError(message);
          toast.error("Generation failed", { description: message });
        }
      } finally {
        if (!cancelled) {
          setBusy(false);
          setRequest(null);
        }
        abort.current = null;
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [request]);

  const leftCatalogue = useCatalogue(left.provider);
  const rightCatalogue = useCatalogue(right.provider);
  const activeSide = mode === "compare" ? right : left;
  const activeCatalogue = mode === "compare" ? rightCatalogue : leftCatalogue;
  const activeProvider = providers.find((p) => p.slug === activeSide.provider);
  const active = resolveSide(activeSide, activeCatalogue, activeProvider);

  const characters = text.trim().length;
  const limit = active.model?.max_chars ?? null;
  const overLimit = Boolean(limit && characters > limit);

  function start() {
    if (!text.trim() && mode !== "dialogue") {
      setError("Enter some text first.");
      return;
    }
    if (overLimit) {
      setError(
        `This model accepts ${limit?.toLocaleString()} characters per request; the text has ${characters.toLocaleString()}.`,
      );
      return;
    }
    setError(null);
    setResult(null);
    setComparison(null);
    setElapsed(0);
    setBusy(true);
    if (mode === "compare") {
      setRequest({
        kind: "compare",
        path: "compare",
        body: {
          text,
          language,
          left: payload(left, resolveSide(left, leftCatalogue, providers.find((p) => p.slug === left.provider))),
          right: payload(right, resolveSide(right, rightCatalogue, providers.find((p) => p.slug === right.provider))),
        },
      });
    } else if (mode === "dialogue") {
      setRequest({
        kind: "dialogue",
        path: "generate-dialogue",
        body: {
          provider: left.provider || null,
          model: active.model?.id ?? null,
          language,
          output_format: active.format?.id ?? null,
          voice_settings: active.settings,
          lines: dialogue
            .filter((l) => l.text.trim())
            .map((l) => ({
              text: l.text,
              voice_id: l.voice_id || active.voice?.voice_id || "",
              speaker: l.speaker,
            })),
        },
      });
    } else {
      setRequest({
        kind: "single",
        path: "generate",
        body: { text, language, ...payload(left, active) },
      });
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="tablist" aria-label="Generation mode" className="flex border border-ink">
          {(
            [
              ["single", "single voice", Sparkles],
              ["compare", "A/B compare", ArrowRightLeft],
              ["dialogue", "dialogue", Users],
            ] as const
          ).map(([key, label, Icon]) => (
            <button
              key={key}
              role="tab"
              aria-selected={mode === key}
              type="button"
              disabled={busy}
              onClick={() => {
                setMode(key);
                setError(null);
              }}
              className={cn(
                "flex h-8 items-center gap-1.5 px-3 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors",
                mode === key ? "bg-ink text-white" : "bg-white text-ink hover:bg-muted",
                key !== "single" && "border-l border-ink",
              )}
            >
              <Icon className="size-3" /> {label}
            </button>
          ))}
        </div>
        <p className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-muted-foreground">
          test generation · never published
        </p>
      </div>

      {!canEdit && (
        <p className="border border-border bg-paper px-3 py-2 text-[12px] text-muted-foreground">
          Your role can browse the studio but not spend credits. Ask an admin for editor access.
        </p>
      )}

      <div
        className={cn(
          "grid gap-5",
          mode === "compare" ? "xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_340px]" : "lg:grid-cols-[minmax(0,1fr)_320px]",
        )}
      >
        <div className={cn("space-y-4", mode === "compare" && "xl:col-span-2")}>
          {mode === "compare" ? (
            <div className="grid gap-4 md:grid-cols-2">
              <SidePanel
                title="A"
                side={left}
                onChange={setLeft}
                provider={providers.find((p) => p.slug === left.provider)}
                catalogue={leftCatalogue}
                providers={usable}
                disabled={busy}
              />
              <SidePanel
                title="B"
                side={right}
                onChange={setRight}
                provider={providers.find((p) => p.slug === right.provider)}
                catalogue={rightCatalogue}
                providers={usable}
                disabled={busy}
              />
            </div>
          ) : (
            <SidePanel
              title={mode === "dialogue" ? "voices" : "voice"}
              side={left}
              onChange={setLeft}
              provider={providers.find((p) => p.slug === left.provider)}
              catalogue={leftCatalogue}
              providers={usable}
              disabled={busy}
            />
          )}

          {mode === "dialogue" ? (
            <DialogueEditor
              lines={dialogue}
              voices={leftCatalogue.voices}
              onChange={setDialogue}
            />
          ) : (
            <Field
              label="text"
              htmlFor="tts-text"
              hint={
                limit
                  ? `${characters.toLocaleString()} / ${limit.toLocaleString()} characters for this model. Long text is split on sentence boundaries and assembled with matched loudness.`
                  : `${characters.toLocaleString()} characters.`
              }
              error={overLimit ? "Text exceeds the selected model's per-request limit" : undefined}
              action={
                <button
                  type="button"
                  onClick={() => setText(SAMPLE)}
                  className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground hover:text-ink"
                >
                  use sample
                </button>
              }
            >
              <Textarea
                id="tts-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={6}
                spellCheck
                placeholder="Paste narration…"
                className={cn("min-h-[132px] text-[13.5px]", overLimit && "border-danger")}
              />
            </Field>
          )}

          <div className="flex flex-wrap items-end gap-3">
            <Field label="language" className="w-[168px]">
              <Select value={language} onChange={(e) => setLanguage(e.target.value)} disabled={busy}>
                {LANGUAGES.map(([code, label]) => (
                  <option key={code} value={code}>
                    {label} · {code}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="flex items-center gap-2 pb-0.5">
              <button
                type="button"
                disabled={!canEdit || busy || overLimit || usable.length === 0}
                onClick={start}
                className={buttonStyles("primary", "md")}
              >
                {busy ? <Loader2 className="animate-spin !size-3.5" /> : <Play className="!size-3.5" />}
                {busy ? `generating · ${elapsed.toFixed(1)}s` : mode === "compare" ? "generate both" : "generate"}
              </button>
              {busy && (
                <button type="button" onClick={() => abort.current?.abort()} className={buttonStyles("outline", "md")}>
                  <Square className="!size-3" /> cancel
                </button>
              )}
            </div>
            {busy && (
              <span className="flex items-center gap-1.5 pb-1 font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
                <span className="h-[2px] w-16 overflow-hidden bg-muted">
                  <span className="block h-full w-1/3 animate-pulse bg-ink" />
                </span>
                contacting {mode === "compare" ? `${left.provider} + ${right.provider}` : left.provider}
              </span>
            )}
          </div>

          {error && (
            <div className="flex items-start gap-2 border border-danger bg-[#FBEBEA] px-3 py-2" role="alert">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-danger" />
              <p className="text-[12.5px] leading-relaxed text-ink">{error}</p>
            </div>
          )}
        </div>

        <div className="space-y-3">
          {mode === "compare" ? (
            <CompareResults
              data={comparison}
              busy={busy}
              onKeep={(side) => {
                setMode("single");
                setLeft(side);
                toast.success("Kept as the single-voice selection");
              }}
            />
          ) : (
            <ResultPanel result={result} />
          )}
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- result

function ResultPanel({ result }: { result: TTSGeneration | null }) {
  const src = audioUrl(result?.audio_url ?? null);
  return (
    <div className="space-y-3">
      <AudioPlayer
        src={src}
        label={result ? `${result.provider} · ${result.voice_id ?? ""}` : "output"}
        caption={result ? `${result.duration_s.toFixed(1)}s · ${result.audio_format ?? ""}` : undefined}
      />
      {result && (
        <dl className="border border-border text-[11.5px]">
          {(
            [
              ["model", result.model],
              ["format", result.audio_format ?? "—"],
              ["chunks", String(result.chunk_count)],
              ["latency", `${(result.latency_ms / 1000).toFixed(2)}s`],
              ["characters", result.characters.toLocaleString()],
              ["est. cost", `$${result.estimated_cost_usd.toFixed(4)}`],
              ["trigger", result.trigger],
            ] as const
          ).map(([key, value]) => (
            <div key={key} className="flex items-baseline justify-between gap-2 border-b border-border px-2.5 py-1 last:border-b-0">
              <dt className="mono-label">{key}</dt>
              <dd className="truncate font-mono text-[10.5px] text-ink" title={value}>
                {value}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {result?.audio_url && (
        <div className="flex flex-wrap items-center gap-1.5">
          <a href={audioUrl(result.audio_url)} download className={buttonStyles("outline", "xs")}>
            <Download className="!size-2.5" /> download
          </a>
          <span className="font-mono text-[9px] uppercase tracking-wider text-subtle">
            {result.id.slice(0, 8)} · test
          </span>
        </div>
      )}
      {result && result.chunk_count > 1 && result.chunk_manifest && (
        <details className="border border-border">
          <summary className="cursor-pointer px-2.5 py-1.5 font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
            <Layers className="mr-1 inline size-3" /> chunk manifest · {result.chunk_count}
          </summary>
          <ol className="scroll-thin max-h-40 overflow-y-auto border-t border-border px-2.5 py-1.5">
            {result.chunk_manifest.map((c) => (
              <li key={c.index} className="flex items-baseline justify-between gap-2 border-b border-dotted border-border py-0.5 font-mono text-[10px] last:border-0">
                <span className="text-subtle">{String(c.index + 1).padStart(2, "0")}</span>
                <span className="flex-1 truncate text-muted-foreground">{c.preview}</span>
                <span className="text-ink">{c.duration_s.toFixed(1)}s</span>
              </li>
            ))}
          </ol>
        </details>
      )}
      {result?.warnings && result.warnings.length > 0 && (
        <ul className="space-y-1 border border-warning bg-[#FDF4DE] px-2.5 py-1.5 text-[11px] text-[#8A6412]">
          {result.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- dialogue

function DialogueEditor({
  lines,
  voices,
  onChange,
}: {
  lines: { speaker: string; text: string; voice_id: string }[];
  voices: TTSVoice[];
  onChange: (lines: { speaker: string; text: string; voice_id: string }[]) => void;
}) {
  return (
    <div className="border border-border">
      <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
        <span className="mono-label text-ink">script · {lines.length} lines</span>
        <span className="font-mono text-[9.5px] uppercase tracking-wider text-subtle">
          2,000 char limit · up to 10 voices
        </span>
      </div>
      <ul className="divide-y divide-border">
        {lines.map((line, i) => (
          <li key={i} className="grid gap-2 px-3 py-2 md:grid-cols-[120px_minmax(0,1fr)_auto] md:items-start">
            <input
              value={line.speaker}
              onChange={(e) => onChange(lines.map((l, j) => (j === i ? { ...l, speaker: e.target.value } : l)))}
              aria-label={`Speaker for line ${i + 1}`}
              className="h-7 border border-border bg-white px-2 font-mono text-[10px] uppercase tracking-wider text-ink focus:border-ink focus:outline-none"
            />
            <textarea
              value={line.text}
              onChange={(e) => onChange(lines.map((l, j) => (j === i ? { ...l, text: e.target.value } : l)))}
              aria-label={`Line ${i + 1}`}
              rows={2}
              className="w-full resize-y border border-border bg-white px-2 py-1 text-[12.5px] leading-snug focus:border-ink focus:outline-none"
            />
            <div className="flex items-center gap-1.5">
              <select
                value={line.voice_id}
                onChange={(e) => onChange(lines.map((l, j) => (j === i ? { ...l, voice_id: e.target.value } : l)))}
                aria-label={`Voice for line ${i + 1}`}
                className="h-7 max-w-[150px] border border-border bg-white px-1 font-mono text-[10px] focus:border-ink focus:outline-none"
              >
                <option value="">default voice</option>
                {voices.map((v) => (
                  <option key={v.voice_id} value={v.voice_id}>
                    {v.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                aria-label={`Remove line ${i + 1}`}
                onClick={() => onChange(lines.filter((_, j) => j !== i))}
                className="grid size-7 place-items-center border border-border text-muted-foreground hover:border-ink hover:text-ink"
              >
                ×
              </button>
            </div>
          </li>
        ))}
      </ul>
      <div className="border-t border-border px-3 py-2">
        <button
          type="button"
          onClick={() => onChange([...lines, { speaker: "Speaker", text: "", voice_id: "" }])}
          className={buttonStyles("outline", "xs")}
        >
          + add line
        </button>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- voice side

function payload(side: Selection, resolved: ReturnType<typeof resolveSide>) {
  return {
    provider: side.provider,
    model: resolved.model?.id ?? null,
    voice_id: resolved.voice?.voice_id ?? null,
    output_format: resolved.format?.id ?? null,
    voice_settings: resolved.settings,
  };
}

function SidePanel({
  title,
  side,
  onChange,
  provider,
  catalogue,
  providers,
  disabled,
}: {
  title: string;
  side: Selection;
  onChange: (s: Selection) => void;
  provider?: TTSProviderRow;
  catalogue: Catalogue & { reload: () => void };
  providers: TTSProviderRow[];
  disabled: boolean;
}) {
  const id = useId();
  const resolved = resolveSide(side, catalogue, provider);
  const { model, voice, format, params, voices, models, formats } = resolved;

  return (
    <div className="border border-border">
      <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
        <span className="flex min-w-0 items-center gap-2">
          <span className="grid size-5 shrink-0 place-items-center bg-ink font-mono text-[10px] text-white">
            {title.slice(0, 1).toUpperCase()}
          </span>
          <span className="mono-label text-ink">{title}</span>
          {provider?.mock && (
            <span className="shrink-0 font-mono text-[9px] uppercase tracking-wider text-[#8A6412]">mock · tone only</span>
          )}
        </span>
        <button
          type="button"
          onClick={catalogue.reload}
          disabled={catalogue.loading}
          className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground hover:text-ink"
          title="Reload models and voices from the provider"
        >
          {catalogue.loading ? <Loader2 className="inline size-3 animate-spin" /> : <RefreshCw className="inline size-3" />} refresh
        </button>
      </div>

      <div className="grid gap-3 px-3 py-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="provider" htmlFor={`${id}-prov`}>
            <Select
              id={`${id}-prov`}
              value={side.provider}
              disabled={disabled}
              onChange={(e) => onChange({ provider: e.target.value, settings: {}, language: "en" })}
            >
              {providers.map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.label}
                  {p.mock ? " (mock)" : ""}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="model" htmlFor={`${id}-model`}>
            <Select
              id={`${id}-model`}
              value={model?.id ?? ""}
              disabled={disabled || !models.length}
              onChange={(e) => onChange({ ...side, model: e.target.value, settings: {} })}
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                  {m.deprecated ? " (deprecated)" : ""}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label={`voice · ${voices.length}`} htmlFor={`${id}-voice`} hint={voice?.description ?? model?.description ?? undefined}>
          <div className="flex gap-1.5">
            <Select
              id={`${id}-voice`}
              value={voice?.voice_id ?? ""}
              disabled={disabled || !voices.length}
              onChange={(e) => onChange({ ...side, voice: e.target.value })}
              className="min-w-0 flex-1"
            >
              {voices.map((v) => (
                <option key={v.voice_id} value={v.voice_id}>
                  {v.name}
                  {v.language ? ` · ${v.language}` : ""}
                  {v.gender ? ` · ${v.gender}` : ""}
                </option>
              ))}
            </Select>
            {voice?.has_preview && (
              <a
                href={previewUrl(voice.preview_endpoint)}
                target="_blank"
                rel="noreferrer"
                className={buttonStyles("outline", "md")}
                title="Open the provider's voice sample in a new tab"
              >
                <Play className="!size-3" /> preview
              </a>
            )}
          </div>
        </Field>

        <Field label="output format" htmlFor={`${id}-fmt`}>
          <Select
            id={`${id}-fmt`}
            value={format?.id ?? ""}
            disabled={disabled || !formats.length}
            onChange={(e) => onChange({ ...side, outputFormat: e.target.value })}
          >
            {formats.map((f) => (
              <option key={f.id} value={f.id}>
                {f.label}
              </option>
            ))}
          </Select>
        </Field>

        {params.length > 0 && (
          <div className="space-y-2.5 border-t border-border pt-2.5">
            <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-subtle">
              voice settings · supported by {model?.name ?? "this model"}
            </p>
            {params.map((p) =>
              p.kind === "boolean" ? (
                <label key={p.key} className="flex items-center justify-between gap-3 text-[12px]">
                  <span className="text-ink" title={p.help ?? undefined}>
                    {p.label}
                  </span>
                  <input
                    type="checkbox"
                    checked={Boolean(resolved.settings[p.key] ?? p.default)}
                    disabled={disabled}
                    onChange={(e) => onChange({ ...side, settings: { ...side.settings, [p.key]: e.target.checked } })}
                    className="size-3.5 accent-[#111]"
                  />
                </label>
              ) : p.kind === "enum" ? (
                <Field key={p.key} label={p.label} hint={p.help ?? undefined}>
                  <Select
                    value={String(resolved.settings[p.key] ?? p.default ?? "")}
                    disabled={disabled}
                    onChange={(e) => onChange({ ...side, settings: { ...side.settings, [p.key]: e.target.value } })}
                  >
                    {p.options.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </Select>
                </Field>
              ) : (
                <RangeField
                  key={p.key}
                  label={p.label}
                  value={Number(resolved.settings[p.key] ?? p.default ?? p.minimum ?? 0)}
                  min={p.minimum ?? 0}
                  max={p.maximum ?? 1}
                  step={(p.maximum ?? 1) - (p.minimum ?? 0) > 2 ? 0.1 : 0.01}
                  defaultValue={typeof p.default === "number" ? p.default : undefined}
                  help={p.help}
                  disabled={disabled}
                  onChange={(v) => onChange({ ...side, settings: { ...side.settings, [p.key]: v } })}
                />
              ),
            )}
          </div>
        )}
        {catalogue.error && <p className="text-[11px] text-danger">{catalogue.error}</p>}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- compare results

function CompareResults({
  data,
  busy,
  onKeep,
}: {
  data: CompareResult | null;
  busy: boolean;
  onKeep: (side: Selection) => void;
}) {
  if (!data) {
    return (
      <div className="border border-dashed border-border bg-paper px-4 py-6">
        <p className="font-serif text-[18px] leading-none text-ink">A/B comparison</p>
        <p className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground">
          {busy
            ? "Generating the same text with both configurations…"
            : "Enter one script, configure two providers and voices, then generate. You will hear both clips with duration, latency and estimated cost side by side."}
        </p>
        <div className="mt-4 grid grid-cols-2 gap-2 border-t border-border pt-3 font-mono text-[9px] uppercase tracking-[0.14em] text-subtle">
          <span>a · provider / voice</span>
          <span>b · provider / voice</span>
        </div>
      </div>
    );
  }
  const sides: [string, CompareSideResult][] = [
    ["A", data.left],
    ["B", data.right],
  ];
  return (
    <div className="space-y-3">
      <div className="border border-ink bg-accent-soft px-3 py-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink">
          {data.verdict.winner ? `${data.verdict.winner} wins` : "verdict"}
        </p>
        <p className="mt-1 text-[12.5px] text-ink">{data.verdict.reason}</p>
        <p className="mt-1 flex flex-wrap gap-x-4 font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
          {data.verdict.cheaper && <span>cheaper · {data.verdict.cheaper === "tie" ? "tie" : data.verdict.cheaper.toUpperCase()}</span>}
          {data.verdict.faster && <span>faster · {data.verdict.faster === "tie" ? "tie" : data.verdict.faster.toUpperCase()}</span>}
          {data.verdict.cost_delta_usd !== undefined && <span>Δ cost ${data.verdict.cost_delta_usd.toFixed(4)}</span>}
          {data.verdict.latency_delta_ms !== undefined && <span>Δ latency {data.verdict.latency_delta_ms} ms</span>}
        </p>
      </div>
      {sides.map(([label, side]) => (
        <div key={label} className={cn("border bg-white", side.ok ? "border-border" : "border-danger bg-[#FBEBEA]")}>
          <div className="flex items-center justify-between border-b border-border px-2.5 py-1.5">
            <span className="mono-label truncate text-ink">
              {label} · {side.provider} · {side.model ?? "default"}
            </span>
            {side.ok ? (
              <button
                type="button"
                onClick={() =>
                  onKeep({
                    provider: side.provider,
                    model: side.model ?? undefined,
                    voice: side.voice_id ?? undefined,
                    outputFormat: side.output_format,
                    settings: {},
                    language: "en",
                  })
                }
                className={buttonStyles("ghost", "xs")}
              >
                <Check className="!size-2.5" /> use {label}
              </button>
            ) : (
              <span className="font-mono text-[9px] uppercase tracking-wider text-danger">failed</span>
            )}
          </div>
          {side.ok ? (
            <div className="space-y-2 p-2.5">
              <AudioPlayer src={audioUrl(side.audio_url ?? null)} caption={side.voice_id ?? undefined} />
              <dl className="grid grid-cols-3 gap-2 font-mono text-[10.5px]">
                <div>
                  <dt className="mono-label">duration</dt>
                  <dd className="text-[12px] text-ink">{(side.duration_s ?? 0).toFixed(1)}s</dd>
                </div>
                <div>
                  <dt className="mono-label">latency</dt>
                  <dd className="text-[12px] text-ink">{(side.latency_ms / 1000).toFixed(2)}s</dd>
                </div>
                <div>
                  <dt className="mono-label">est. cost</dt>
                  <dd className="text-[12px] text-ink">${(side.estimated_cost_usd ?? 0).toFixed(4)}</dd>
                </div>
              </dl>
              {side.warnings && side.warnings.length > 0 && (
                <p className="text-[10.5px] text-[#8A6412]">{side.warnings.join(" ")}</p>
              )}
            </div>
          ) : (
            <p className="px-2.5 py-2 text-[12px] text-danger">{side.error ?? "Generation failed"}</p>
          )}
        </div>
      ))}
    </div>
  );
}
