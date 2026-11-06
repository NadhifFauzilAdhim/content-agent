"use client";

import { useCallback, useId, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, Loader2, ShieldCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { buttonStyles } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { StatusChip } from "@/components/ui/status";
import { googleClient, type GoogleClient } from "@/lib/studio";

/**
 * Google OAuth client editor for the youtube/google provider.
 *
 * The client id and secret are stored in the credential vault (AES-256-GCM), so an operator can
 * configure Google sign-in from the dashboard instead of editing `.env` and restarting. Values set
 * here take precedence over `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
 */
export function GoogleClientPanel({ canManage }: { canManage: boolean }) {
  const router = useRouter();
  const id = useId();
  const [client, setClient] = useState<GoogleClient | null>(null);
  const [clientId, setClientId] = useState("");
  const [secret, setSecret] = useState("");
  const [pending, setPending] = useState<"save" | "clear" | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const load = useCallback(async () => {
    try {
      setClient(await googleClient());
    } catch {
      setClient(null);
    }
  }, []);

  // Loaded once from a user action rather than an effect: the panel starts closed anyway, and the
  // server-rendered page already knows whether the provider has a credential.
  const [loaded, setLoaded] = useState(false);
  function ensureLoaded() {
    if (!loaded) {
      setLoaded(true);
      void load();
    }
  }

  async function save() {
    setPending("save");
    try {
      const next = await googleClient({
        method: "PUT",
        body: { client_id: clientId.trim(), client_secret: secret.trim() },
      });
      setClient(next);
      setClientId("");
      setSecret("");
      toast.success("Google OAuth client saved", {
        description: "Channels can connect immediately — no restart needed.",
      });
      router.refresh();
    } catch (err) {
      toast.error("Could not save the client", { description: (err as Error).message });
    } finally {
      setPending(null);
    }
  }

  async function clear() {
    setPending("clear");
    try {
      await googleClient({ method: "DELETE" });
      setConfirmClear(false);
      await load();
      toast.success("Dashboard client removed", {
        description: client?.env_fallback
          ? "The environment values take over again."
          : "Add a client id and secret to enable YouTube connections.",
      });
      router.refresh();
    } catch (err) {
      toast.error("Could not remove the client", { description: (err as Error).message });
    } finally {
      setPending(null);
    }
  }

  const hasUsableSecret = Boolean(client?.has_secret) || client?.source === "environment";
  const canSave =
    clientId.trim().endsWith(".apps.googleusercontent.com") &&
    (secret.trim().length >= 8 || hasUsableSecret);

  return (
    <div
      id={`${id}-google`}
      className="border-t border-ink bg-paper px-3 pb-4 pt-3"
      onFocusCapture={ensureLoaded}
      onPointerEnter={ensureLoaded}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2">
          <ShieldCheck className="size-3.5 text-ink" />
          <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-muted-foreground">
            google oauth client
          </span>
          {client?.configured ? (
            <StatusChip tone="success" dot={false}>
              {client.source === "dashboard" ? "from dashboard" : "from environment"}
            </StatusChip>
          ) : (
            <StatusChip tone="idle" dot={false}>
              not configured
            </StatusChip>
          )}
        </span>
        {client?.client_id_masked && (
          <span className="font-mono text-[9.5px] uppercase tracking-wider text-subtle">
            {client.client_id_masked}
          </span>
        )}
      </div>

      {!canManage ? (
        <p className="text-[12px] text-muted-foreground">
          Only workspace admins can change the Google OAuth client.
        </p>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-2">
            <Field
              label="client id"
              hint="Google Cloud → APIs & Services → Credentials → OAuth client"
              htmlFor={`${id}-cid`}
            >
              <Input
                id={`${id}-cid`}
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                placeholder="123456789-abc.apps.googleusercontent.com"
                autoComplete="off"
                spellCheck={false}
              />
            </Field>
            <Field
              label={client?.has_secret ? "rotate client secret" : "client secret"}
              hint={
                client?.has_secret
                  ? "Leave blank to keep the stored secret while changing the id."
                  : "Encrypted with AES-256-GCM and never returned by the API."
              }
              htmlFor={`${id}-sec`}
            >
              <Input
                id={`${id}-sec`}
                type="password"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder={client?.has_secret ? "unchanged" : "GOCSPX-…"}
                autoComplete="off"
              />
            </Field>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <p className="max-w-[52ch] text-[11.5px] leading-relaxed text-muted-foreground">
              Authorized redirect URI:{" "}
              <code className="font-mono text-[10.5px] text-ink">{client?.redirect_uri ?? "…"}</code>
            </p>
            <div className="flex items-center gap-2">
              {confirmClear ? (
                <>
                  <span className="font-mono text-[9.5px] uppercase tracking-wider text-[#9B2C28]">
                    remove stored client?
                  </span>
                  <button
                    type="button"
                    disabled={pending !== null}
                    onClick={clear}
                    className={buttonStyles("danger", "xs")}
                  >
                    {pending === "clear" && <Loader2 className="animate-spin !size-2.5" />} remove
                  </button>
                  <button
                    type="button"
                    disabled={pending !== null}
                    onClick={() => setConfirmClear(false)}
                    className={buttonStyles("ghost", "xs")}
                  >
                    cancel
                  </button>
                </>
              ) : (
                <>
                  {client?.source === "dashboard" && (
                    <button
                      type="button"
                      onClick={() => setConfirmClear(true)}
                      className={buttonStyles("ghost", "xs")}
                    >
                      <Trash2 className="!size-2.5" /> remove
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={pending !== null || !canSave}
                    onClick={save}
                    className={buttonStyles("primary", "xs")}
                    title={canSave ? undefined : "A Google client id and secret are required"}
                  >
                    {pending === "save" ? (
                      <Loader2 className="animate-spin !size-2.5" />
                    ) : (
                      <CheckCircle2 className="!size-2.5" />
                    )}{" "}
                    save client
                  </button>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
