"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Save, Volume2 } from "lucide-react";
import { toast } from "sonner";

import type { TTSProviderRow } from "@/lib/types";
import { studio, StudioError } from "@/lib/studio";
import { buttonStyles } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/input";
import { StatusChip } from "@/components/ui/status";

export type VoiceSettingsState = {
  provider: string;
  fallback_provider: string | null;
  model: string | null;
  voice_id: string | null;
  language: string | null;
  output_format: string | null;
} | null;

/**
 * Global text-to-speech default. This is the least specific level of the inheritance chain
 * (scene → workflow → channel → workspace); the voice agent and Audio Studio both read it.
 */
export function VoiceDefaults({
  providers,
  current,
  canManage,
}: {
  providers: TTSProviderRow[];
  current: VoiceSettingsState;
  canManage: boolean;
}) {
  const router = useRouter();
  const usable = providers.filter((p) => p.usable);
  const [provider, setProvider] = useState(current?.provider ?? usable[0]?.slug ?? "mock");
  const [fallback, setFallback] = useState(current?.fallback_provider ?? "");
  const [model, setModel] = useState(current?.model ?? "");
  const [voice, setVoice] = useState(current?.voice_id ?? "");
  const [language, setLanguage] = useState(current?.language ?? "");
  const [pending, setPending] = useState(false);

  async function save() {
    setPending(true);
    try {
      await studio("settings", {
        method: "PUT",
        body: {
          provider,
          fallback_provider: fallback || null,
          model: model || null,
          voice_id: voice || null,
          language: language || null,
          output_format: null,
          voice_settings: {},
        },
      });
      toast.success("Voice defaults saved", { description: "Inherited by channels, workflows and scenes unless overridden." });
      router.refresh();
    } catch (err) {
      toast.error("Could not save", { description: err instanceof StudioError ? err.message : (err as Error).message });
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-3">
        <Field label="default provider" hint={canManage ? undefined : "Admins only"}>
          <Select value={provider} onChange={(e) => setProvider(e.target.value)} disabled={!canManage}>
            {usable.map((p) => (
              <option key={p.slug} value={p.slug}>
                {p.label}
                {p.mock ? " (mock)" : ""}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="fallback provider" hint="Used only for transient outages, timeouts and exhausted rate limits.">
          <Select value={fallback} onChange={(e) => setFallback(e.target.value)} disabled={!canManage}>
            <option value="">none</option>
            {usable
              .filter((p) => p.slug !== provider)
              .map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.label}
                </option>
              ))}
          </Select>
        </Field>
        <Field label="language" hint="Blank inherits the channel language.">
          <Select value={language} onChange={(e) => setLanguage(e.target.value)} disabled={!canManage}>
            <option value="">channel default</option>
            {["en", "es", "fr", "de", "it", "pt", "ja", "ko", "zh", "hi", "ar"].map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="model override" hint="Blank uses the provider's default model.">
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={!canManage}
            placeholder="provider default"
            className="h-8 w-full border border-border bg-white px-3 font-mono text-[12px] focus:border-ink focus:outline-none disabled:bg-muted"
          />
        </Field>
        <Field label="voice override" className="md:col-span-2" hint="Voice ids are provider-specific — choose the voice in Audio Studio and copy its id.">
          <input
            value={voice}
            onChange={(e) => setVoice(e.target.value)}
            disabled={!canManage}
            placeholder="provider default"
            className="h-8 w-full border border-border bg-white px-3 font-mono text-[12px] focus:border-ink focus:outline-none disabled:bg-muted"
          />
        </Field>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-mono text-[9.5px] uppercase tracking-[0.12em] text-subtle">
          <Volume2 className="size-3" />
          precedence: scene → workflow → channel → workspace{" "}
          {current && <StatusChip tone="success">configured</StatusChip>}
        </p>
        {canManage && (
          <button type="button" onClick={save} disabled={pending} className={buttonStyles("primary", "sm")}>
            {pending ? <Loader2 className="animate-spin !size-3" /> : <Save className="!size-3" />} save voice defaults
          </button>
        )}
      </div>
    </div>
  );
}
