"use client";

import { useId, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Plug,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import type { Provider } from "@/lib/types";
import { providerCredentials, StudioError } from "@/lib/studio";
import { buttonStyles } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { StatusChip } from "@/components/ui/status";
import { cn } from "@/lib/utils";

type CredentialState = {
  has_credential: boolean;
  status: string;
  version: number;
  fingerprint: string | null;
  updated_at: string | null;
  encryption_ready: boolean;
  problem: string | null;
};

const TTS_DEFAULTS: Record<string, { model: string; voice: string; format: string; voiceLabel: string }> = {
  cartesia: {
    model: "sonic-3.6",
    voice: "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",
    format: "wav/44100/pcm_s16le",
    voiceLabel: "Skylar · en-US",
  },
  elevenlabs: {
    model: "eleven_multilingual_v2",
    voice: "21m00Tcm4TlvDq8ikWAM",
    format: "mp3_44100_128",
    voiceLabel: "Rachel · en",
  },
};

/**
 * Centralised credential editor for one provider — the same component for LLM, TTS, image and
 * YouTube adapters. Adapters that expose extra defaults (TTS: model / voice / output format) get
 * those fields too, so the voice agent inherits a usable configuration.
 */
export function CredentialPanel({
  provider,
  canManage,
  onChanged,
  children,
  open = true,
  panelId,
}: {
  provider: Provider;
  canManage: boolean;
  onChanged: () => void;
  children?: ReactNode;
  open?: boolean;
  panelId?: string;
}) {
  const id = useId();
  const tts = provider.kind === "tts" ? TTS_DEFAULTS[provider.slug] : undefined;
  const [key, setKey] = useState("");
  const [reveal, setReveal] = useState(false);
  const [model, setModel] = useState(provider.extra_config?.default_model ?? tts?.model ?? "");
  const [voice, setVoice] = useState(provider.extra_config?.default_voice_id ?? tts?.voice ?? "");
  const [format, setFormat] = useState(provider.extra_config?.default_output_format ?? tts?.format ?? "");
  const [pending, setPending] = useState<"save" | "remove" | "test" | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [test, setTest] = useState<{ ok: boolean; detail: string } | null>(null);
  const [state, setState] = useState<CredentialState>({
    has_credential: provider.has_credential,
    status: provider.credential_status,
    version: provider.credential_version,
    fingerprint: provider.credential_fingerprint,
    updated_at: provider.credential_updated_at,
    encryption_ready: true,
    problem: null,
  });

  async function save() {
    if (!key.trim()) {
      toast.error("Enter the new key first", { description: "Empty fields never replace a stored key." });
      return;
    }
    setPending("save");
    try {
      const result = await providerCredentials(provider.kind, provider.slug, {
        method: "POST",
        body: {
          api_key: key.trim(),
          default_model: model || null,
          default_voice_id: voice || null,
          default_output_format: format || null,
        },
      });
      setState({ ...result });
      setKey("");
      setReveal(false);
      toast.success(`${provider.name} credential saved`, {
        description: `Encrypted · version ${result.version} · ${result.fingerprint ?? ""}`,
      });
      onChanged();
    } catch (err) {
      toast.error("Could not save the key", { description: (err as Error).message });
    } finally {
      setPending(null);
    }
  }

  async function testConnection() {
    setPending("test");
    setTest(null);
    try {
      const res = await fetch(`/api/proxy/providers/${provider.id}/test`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        throw new StudioError({ code: "http", message: data?.error?.message ?? "Test failed", status: res.status });
      }
      setTest({ ok: Boolean(data.ok), detail: String(data.detail ?? "") });
      onChanged();
    } catch (err) {
      setTest({ ok: false, detail: (err as Error).message });
    } finally {
      setPending(null);
    }
  }

  async function remove() {
    setPending("remove");
    try {
      const result = await providerCredentials(provider.kind, provider.slug, { method: "DELETE" });
      setState({ ...result });
      setConfirmRemove(false);
      toast.success("Credential removed", { description: "Stored secret shredded. History kept." });
      onChanged();
    } catch (err) {
      toast.error("Could not remove the credential", { description: (err as Error).message });
    } finally {
      setPending(null);
    }
  }

  const { fingerprint, status, has_credential: hasKey } = state;
  if (!open) return null;

  return (
    <div id={panelId} className="mt-2 w-[min(760px,calc(100vw-6rem))] border border-ink bg-paper text-left">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-1.5">
        <span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink">
          <KeyRound className="size-3" /> credentials
          {status === "active" && <StatusChip tone="success">active</StatusChip>}
          {status === "unset" && <StatusChip tone="idle" dot={false}>not set</StatusChip>}
          {status === "disabled" && <StatusChip tone="danger" dot={false}>removed</StatusChip>}
        </span>
        <span className="flex items-center gap-3 font-mono text-[9.5px] uppercase tracking-[0.12em] text-subtle">
          <span>v{state.version}</span>
          <span>{fingerprint ?? "no fingerprint"}</span>
        </span>
      </div>

      {!canManage ? (
        <p className="px-3 py-2.5 text-[12px] text-muted-foreground">
          Only workspace admins can add or rotate API keys. Ask an admin to update this provider.
        </p>
      ) : provider.is_mock ? (
        <p className="px-3 py-2.5 text-[12px] text-muted-foreground">
          The mock adapter is local — it never calls a provider and needs no credentials.
        </p>
      ) : (
        <div className="grid gap-3 px-3 py-3 md:grid-cols-2">
          <Field
            label={hasKey ? "rotate api key" : "api key"}
            hint={
              hasKey
                ? "Leave blank to keep the current key. A blank field never overwrites it."
                : `${
                    provider.slug === "cartesia"
                      ? "Starts with sk_car_…"
                      : provider.slug === "elevenlabs"
                        ? "From Profile → API keys"
                        : "Paste the provider key"
                  } — encrypted with AES-256-GCM before it is stored.`
            }
            htmlFor={`${id}-key`}
            className="md:col-span-2"
            action={
              <button
                type="button"
                onClick={() => setReveal((v) => !v)}
                aria-label={reveal ? "Hide key" : "Show key"}
                className="font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground hover:text-ink"
              >
                {reveal ? <EyeOff className="inline size-3" /> : <Eye className="inline size-3" />} {reveal ? "hide" : "show"}
              </button>
            }
          >
            <Input
              id={`${id}-key`}
              type={reveal ? "text" : "password"}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder={hasKey ? `${fingerprint ?? "configured"} — enter a new key to rotate` : "paste key"}
              autoComplete="off"
              spellCheck={false}
              className="font-mono text-[12px]"
            />
          </Field>

          {tts && (
            <>
              <Field label="default model" hint="Inherited by the voice agent unless a channel or workflow overrides it.">
                <Input value={model} onChange={(e) => setModel(e.target.value)} className="font-mono text-[12px]" />
              </Field>
              <Field label={`default voice · ${tts.voiceLabel}`} hint="Voice id — pick another in Audio Studio.">
                <Input value={voice} onChange={(e) => setVoice(e.target.value)} className="font-mono text-[12px]" />
              </Field>
              <Field
                label="default output format"
                className="md:col-span-2"
                hint="wav/44100/pcm_s16le for Cartesia · mp3_44100_128 for ElevenLabs."
              >
                <Input value={format} onChange={(e) => setFormat(e.target.value)} className="font-mono text-[12px]" />
              </Field>
            </>
          )}

          <div className="flex flex-wrap items-center gap-1.5 md:col-span-2">
            <button type="button" disabled={pending !== null || !key.trim()} onClick={save} className={buttonStyles("primary", "sm")}>
              {pending === "save" ? <Loader2 className="animate-spin !size-3" /> : <ShieldCheck className="!size-3" />}
              {hasKey ? "rotate key" : "save key"}
            </button>
            <button type="button" disabled={pending !== null || !hasKey} onClick={testConnection} className={buttonStyles("outline", "sm")}>
              {pending === "test" ? <Loader2 className="animate-spin !size-3" /> : <Plug className="!size-3" />} test connection
            </button>
            {hasKey && !confirmRemove && (
              <button type="button" disabled={pending !== null} onClick={() => setConfirmRemove(true)} className={buttonStyles("ghost", "sm", "text-danger")}>
                <Trash2 className="!size-3" /> remove
              </button>
            )}
            {confirmRemove && (
              <span className="flex flex-wrap items-center gap-1.5 border border-danger bg-[#FBEBEA] px-2 py-1 text-[11px] text-danger">
                <AlertTriangle className="size-3" /> Delete the stored key? History stays; generation stops.
                <button type="button" disabled={pending !== null} onClick={remove} className="font-mono text-[10px] uppercase underline underline-offset-2">
                  {pending === "remove" ? "removing…" : "confirm"}
                </button>
                <button type="button" onClick={() => setConfirmRemove(false)} className="font-mono text-[10px] uppercase text-ink underline underline-offset-2">
                  cancel
                </button>
              </span>
            )}
          </div>

          {test && (
            <p
              className={cn(
                "border px-2.5 py-1.5 font-mono text-[10.5px] uppercase tracking-wider md:col-span-2",
                test.ok ? "border-success bg-[#F3FBDD] text-[#4B6B0D]" : "border-danger bg-[#FBEBEA] text-danger",
              )}
              role="status"
            >
              {test.ok ? "connected" : "failed"} · {test.detail || "no detail"}
            </p>
          )}
          {state.problem && <p className="text-[11px] text-danger md:col-span-2">{state.problem}</p>}
          <p className="font-mono text-[9.5px] uppercase leading-relaxed tracking-[0.12em] text-subtle md:col-span-2">
            Key changes apply immediately — no restart — and are written to the audit log as{" "}
            <span className="text-muted-foreground">provider.credentials.updated</span>.
          </p>
          {children}
        </div>
      )}
    </div>
  );
}
