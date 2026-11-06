"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, ListTree, Loader2, Plug, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import type { Provider } from "@/lib/types";
import { buttonStyles } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";
import { CredentialPanel } from "./credential-panel";

const ADAPTERS: Record<string, { slug: string; label: string; base?: string; models: string; help: string }[]> = {
  llm: [
    { slug: "openai", label: "OpenAI", base: "https://api.openai.com/v1", models: "gpt-4.1-mini, gpt-4.1", help: "Platform API key (sk-…). Models receive the JSON schema for structured output." },
    { slug: "gemini", label: "Google Gemini", models: "gemini-2.5-flash", help: "Google AI Studio API key. Uses responseSchema for structured output." },
    {
      slug: "openai-compatible",
      label: "OpenAI-compatible",
      models: "",
      help: "Any endpoint that speaks the OpenAI Chat Completions API — Groq, Together, Fireworks, OpenRouter, DeepSeek, Mistral, xAI, Ollama, LM Studio, vLLM, LiteLLM or your own gateway. Enter the base URL ending in /v1, then discover the models your endpoint exposes.",
    },
    {
      slug: "anthropic-compatible",
      label: "Anthropic-compatible",
      models: "",
      help: "Any endpoint that speaks the Anthropic Messages API (POST /messages with x-api-key). Enter the base URL ending in /v1. Model discovery is best effort — type the models if your gateway does not publish a list.",
    },
    { slug: "mock", label: "Mock (development)", models: "mock-structured", help: "Deterministic fixtures — for pipeline testing only." },
  ],
  tts: [
    { slug: "cartesia", label: "Cartesia", models: "sonic-2", help: "Cartesia API key. Sonic voices return WAV audio per scene." },
    { slug: "elevenlabs", label: "ElevenLabs", models: "eleven_multilingual_v2", help: "ElevenLabs API key. MP3 at 44.1 kHz." },
    { slug: "mock", label: "Mock (development)", models: "mock-tts", help: "Silent tone at the estimated speech length." },
  ],
  image: [
    { slug: "openai", label: "OpenAI Images", base: "https://api.openai.com/v1", models: "gpt-image-1", help: "gpt-image-1 supports 16:9 and 9:16 sizes." },
    { slug: "gemini", label: "Gemini Images", models: "gemini-2.5-flash-image", help: "Image generation via generateContent." },
    { slug: "mock", label: "Mock (development)", models: "mock-image", help: "Pillow storyboard cards — clearly marked MOCK." },
  ],
  youtube: [
    { slug: "google", label: "YouTube (Google OAuth)", models: "v3", help: "Requires GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET on the API server. Channels connect individually." },
    { slug: "mock", label: "Mock (development)", models: "v3", help: "Records uploads without contacting YouTube." },
  ],
};

const COMPATIBLE = new Set(["openai-compatible", "anthropic-compatible"]);

export function AddProvider({ existing }: { existing: Provider[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<"llm" | "tts" | "image" | "youtube">("llm");
  const [slug, setSlug] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [models, setModels] = useState("gpt-4.1-mini");
  const [baseUrl, setBaseUrl] = useState("");
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);
  const [discovering, setDiscovering] = useState(false);

  const adapter = ADAPTERS[kind].find((a) => a.slug === slug) ?? ADAPTERS[kind][0];
  const isCompatible = COMPATIBLE.has(adapter.slug);
  const taken = (k: string, s: string) => existing.some((p) => p.kind === k && p.slug === s);

  function selectAdapter(next: string) {
    const a = ADAPTERS[kind].find((x) => x.slug === next)!;
    setSlug(a.slug);
    setModels(a.models);
    setBaseUrl(COMPATIBLE.has(a.slug) ? "" : (a.base ?? ""));
  }

  async function submit() {
    setPending(true);
    try {
      const listed = models.split(/[,\n]/).map((m) => m.trim()).filter(Boolean);
      const res = await fetch("/api/proxy/providers", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          kind,
          slug: adapter.slug,
          name: isCompatible && name.trim() ? name.trim() : adapter.label,
          vendor: isCompatible ? (name.trim().split(" ")[0] || adapter.label.split(" ")[0]) : adapter.label.split(" ")[0],
          base_url: isCompatible ? baseUrl.trim() || null : (adapter.base ?? null),
          api_key: adapter.slug === "mock" ? null : apiKey || null,
          models: listed.map((id) => ({ id })),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "Could not add provider");
      const created = data as { id: string };
      // Compatible endpoints: ask the server to read the model list straight from the endpoint.
      if (isCompatible && created?.id) {
        await fetch(`/api/proxy/providers/${created.id}/models?refresh=true&persist=true`)
          .then((r) => r.json())
          .then((d) => {
            if (Array.isArray(d?.models) && d.models.length) {
              toast.success(`${adapter.label} added`, { description: `${d.models.length} models discovered` });
            }
          })
          .catch(() => undefined);
      } else {
        toast.success(`${adapter.label} added`, { description: "Run a connection test to verify it." });
      }
      setOpen(false);
      setApiKey("");
      setBaseUrl("");
      setName("");
      router.refresh();
    } catch (err) {
      toast.error("Provider rejected", { description: (err as Error).message });
    } finally {
      setPending(false);
    }
  }

  async function discover() {
    if (!baseUrl.trim() || !apiKey) {
      toast.error("Base URL and API key are needed to discover models");
      return;
    }
    setDiscovering(true);
    try {
      const res = await fetch("/api/proxy/providers/discover-models", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ slug: adapter.slug, base_url: baseUrl.trim(), api_key: apiKey }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "Discovery failed");
      const found: { id: string }[] = Array.isArray(data?.models) ? data.models : [];
      if (!found.length) {
        toast.error("No models reported", { description: data?.error ?? "This endpoint does not publish /models — type them manually." });
        return;
      }
      setModels(found.map((m) => m.id).join(", "));
      toast.success(`${found.length} models found`, { description: found.slice(0, 4).map((m) => m.id).join(", ") + (found.length > 4 ? " …" : "") });
    } catch (err) {
      toast.error("Could not list models", { description: (err as Error).message });
    } finally {
      setDiscovering(false);
    }
  }

  return (
    <div>
      <button type="button" onClick={() => setOpen((v) => !v)} className={buttonStyles("accent", "md")}>
        {open ? <X className="!size-3" /> : <Plus className="!size-3" />} {open ? "close" : "add provider"}
      </button>
      {open && (
        <div className="mt-3 border border-ink bg-paper p-4 animate-slide-up">
          <div className="grid gap-3 md:grid-cols-4">
            <Field label="kind">
              <Select
                value={kind}
                onChange={(e) => {
                  const k = e.target.value as typeof kind;
                  setKind(k);
                  setSlug(ADAPTERS[k][0].slug);
                  setModels(ADAPTERS[k][0].models);
                  setBaseUrl(ADAPTERS[k][0].base ?? "");
                }}
              >
                <option value="llm">LLM</option>
                <option value="tts">Text to speech</option>
                <option value="image">Image</option>
                <option value="youtube">YouTube</option>
              </Select>
            </Field>
            <Field label="adapter">
              <Select value={slug} onChange={(e) => selectAdapter(e.target.value)}>
                {ADAPTERS[kind].map((a) => (
                  <option key={a.slug} value={a.slug} disabled={taken(kind, a.slug)}>
                    {a.label}{taken(kind, a.slug) ? " · added" : ""}
                  </option>
                ))}
              </Select>
            </Field>
            {isCompatible ? (
              <Field label="display name" hint="how it appears in this workspace">
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={adapter.label} />
              </Field>
            ) : (
              <Field label="models · comma separated">
                <Input value={models} onChange={(e) => setModels(e.target.value)} />
              </Field>
            )}
            <Field label="api key" hint={adapter.slug === "mock" ? "not required" : "encrypted at rest"}>
              <Input
                type="password"
                value={apiKey}
                disabled={adapter.slug === "mock" || kind === "youtube"}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={kind === "youtube" ? "via server env" : isCompatible ? "your provider key" : "sk-…"}
                autoComplete="off"
              />
            </Field>
          </div>

          {isCompatible && (
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              <Field label="base url" hint="must end in /v1">
                <Input
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder={adapter.slug === "openai-compatible" ? "https://api.groq.com/openai/v1" : "https://api.anthropic.com/v1"}
                  autoComplete="off"
                  spellCheck={false}
                />
              </Field>
              <div className="md:col-span-2">
                <Field label="models · discovered or comma separated">
                  <Input value={models} onChange={(e) => setModels(e.target.value)} placeholder="discover below, or type model ids" />
                </Field>
              </div>
            </div>
          )}

          <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">{adapter.help}</p>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {isCompatible && (
                <button type="button" disabled={discovering} onClick={discover} className={buttonStyles("outline", "sm")}>
                  {discovering ? <Loader2 className="animate-spin !size-3" /> : <ListTree className="!size-3" />} list models
                </button>
              )}
              <p className="font-mono text-[9.5px] uppercase tracking-wider text-subtle">
                keys are encrypted (AES-256-GCM) and never returned by the API
              </p>
            </div>
            <button
              type="button"
              disabled={pending || (isCompatible && (!baseUrl.trim() || !models.trim()))}
              onClick={submit}
              className={buttonStyles("primary", "sm")}
              title={isCompatible && !baseUrl.trim() ? "A base URL is required" : undefined}
            >
              {pending && <Loader2 className="animate-spin !size-3" />} save provider
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function CredentialToggle({
  provider,
  open,
  onToggle,
}: {
  provider: Provider;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-expanded={open}
      aria-controls={`credential-${provider.id}`}
      onClick={onToggle}
      className={buttonStyles("outline", "xs")}
    >
      <KeyRound className="!size-2.5" />
      {open ? "close" : provider.has_credential ? "manage key" : "add key"}
    </button>
  );
}

export function CredentialRow({ provider, canManage }: { provider: Provider; canManage: boolean }) {
  const router = useRouter();
  return (
    <tr id={`credential-${provider.id}`} className="border-b border-ink">
      <td colSpan={6} className="bg-paper px-0 py-0">
        <div className="px-3 pb-4 pt-1">
          <CredentialPanel provider={provider} canManage={canManage} onChanged={() => router.refresh()} />
        </div>
      </td>
    </tr>
  );
}

export function ProviderActions({ provider, canManage }: { provider: Provider; canManage: boolean }) {
  const router = useRouter();
  const [pending, setPending] = useState<"test" | "toggle" | "delete" | "models" | null>(null);
  const [confirming, setConfirming] = useState(false);

  async function test() {
    setPending("test");
    try {
      const res = await fetch(`/api/proxy/providers/${provider.id}/test`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "Test failed");
      if (data.ok) toast.success(`${provider.name}: connected`, { description: data.detail });
      else toast.error(`${provider.name}: not reachable`, { description: data.detail });
      router.refresh();
    } catch (err) {
      toast.error("Connection test failed", { description: (err as Error).message });
    } finally {
      setPending(null);
    }
  }

  async function toggle() {
    setPending("toggle");
    try {
      const res = await fetch(`/api/proxy/providers/${provider.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ is_enabled: !provider.is_enabled }),
      });
      if (!res.ok) throw new Error((await res.json())?.error?.message ?? "Update failed");
      toast.success(provider.is_enabled ? `${provider.name} disabled` : `${provider.name} enabled`);
      router.refresh();
    } catch (err) {
      toast.error("Could not update", { description: (err as Error).message });
    } finally {
      setPending(null);
    }
  }

  async function refreshModels() {
    setPending("models");
    try {
      const res = await fetch(`/api/proxy/providers/${provider.id}/models?refresh=true&persist=true`);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "Could not list models");
      if (data.discovered) {
        toast.success(`${provider.name}: ${data.models.length} models`, {
          description: data.models.slice(0, 5).map((m: { id: string }) => m.id).join(", ") + (data.models.length > 5 ? " …" : ""),
        });
        router.refresh();
      } else {
        toast.error("No model list published", {
          description: data.error ?? "This endpoint does not expose /models — add models manually.",
        });
      }
    } catch (err) {
      toast.error("Model discovery failed", { description: (err as Error).message });
    } finally {
      setPending(null);
    }
  }

  async function remove() {
    setPending("delete");
    try {
      const res = await fetch(`/api/proxy/providers/${provider.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error((await res.json())?.error?.message ?? "Delete failed");
      toast.success(`${provider.name} deleted`, {
        description: "Credentials and configuration removed. Usage history is kept for accounting.",
      });
      setConfirming(false);
      router.refresh();
    } catch (err) {
      toast.error("Could not delete provider", { description: (err as Error).message });
    } finally {
      setPending(null);
    }
  }

  const supportsDiscovery = provider.slug === "openai-compatible" || provider.slug === "anthropic-compatible";

  return (
    <div className="flex flex-col gap-2">
      {confirming ? (
        <div className="flex flex-wrap items-center justify-end gap-1.5 border border-[#9B2C28] bg-[#FBEBEA] px-2 py-1.5">
          <span className="font-mono text-[9.5px] uppercase tracking-wider text-[#9B2C28]">delete permanently?</span>
          <button
            type="button"
            disabled={pending !== null}
            onClick={remove}
            className={buttonStyles("danger", "xs")}
          >
            {pending === "delete" && <Loader2 className="animate-spin !size-2.5" />} delete
          </button>
          <button type="button" disabled={pending !== null} onClick={() => setConfirming(false)} className={buttonStyles("ghost", "xs")}>
            cancel
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          <button
            type="button"
            disabled={pending !== null || !canManage}
            onClick={test}
            className={buttonStyles("outline", "xs")}
            title={canManage ? "Run a live connection test" : "Requires the editor role"}
          >
            {pending === "test" ? <Loader2 className="animate-spin !size-2.5" /> : <Plug className="!size-2.5" />} test
          </button>
          <button
            type="button"
            disabled={pending !== null || !canManage}
            onClick={toggle}
            className={buttonStyles(provider.is_enabled ? "ghost" : "secondary", "xs")}
          >
            {provider.is_enabled ? "disable" : "enable"}
          </button>
          {supportsDiscovery && (
            <button
              type="button"
              disabled={pending !== null || !canManage || !provider.has_credential}
              onClick={refreshModels}
              className={buttonStyles("ghost", "xs")}
              title={provider.has_credential ? "Read the model list from this endpoint" : "Save an API key first"}
            >
              {pending === "models" ? <Loader2 className="animate-spin !size-2.5" /> : <RefreshCw className="!size-2.5" />} models
            </button>
          )}
          <button
            type="button"
            disabled={pending !== null || !canManage}
            onClick={() => setConfirming(true)}
            className={buttonStyles("ghost", "xs")}
            title={canManage ? "Delete this provider and its credentials" : "Requires the admin role"}
          >
            <Trash2 className="!size-2.5" /> delete
          </button>
        </div>
      )}
    </div>
  );
}


