import { KeyRound, ShieldCheck } from "lucide-react";

import { api, resources, sessionToken } from "@/lib/api";
import { AddProvider } from "./provider-actions";
import { ProviderSections } from "./provider-sections";
import { RefreshButton } from "@/components/domain/actions";
import { PageHeader, Section, SectionTitle } from "@/components/ui/layout";
import { MetricStrip } from "@/components/ui/metrics";
import { SetupState } from "@/components/ui/states";

export const metadata = { title: "Providers" };

export default async function ProvidersPage() {
  const token = await sessionToken();
  const [providers, integrations, encryption, session] = await Promise.all([
    resources.providers(),
    resources.integrations(),
    api<{ ready: boolean; problem: string | null; algorithm: string }>("/providers/encryption", { token }),
    resources.session(),
  ]);
  const canManage = ["owner", "admin"].includes(session.workspace.role);
  const ready = providers.filter((p) => p.is_enabled && !p.is_mock && (p.has_credential || p.kind === "youtube"));
  const mocks = providers.filter((p) => p.is_mock);
  const errors = providers.filter((p) => p.health === "error" || p.health === "degraded");

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Factory" }, { label: "Providers" }, { label: "Settings" }]}
        title="Provider"
        italic="registry"
        description="Every external capability sits behind a port. Credentials are sealed with AES-256-GCM (authenticated encryption) using APP_ENCRYPTION_KEY, never returned to the browser, and only decrypted inside the API process when an adapter makes a call."
        actions={<RefreshButton />}
      />

      {!encryption.ready && (
        <div className="mt-6">
          <SetupState
            title="Encryption key is missing or invalid"
            description={encryption.problem ?? "Set APP_ENCRYPTION_KEY to a 32-byte key."}
            steps={[
              { label: "Run `python -m app.cli gen-key` in apps/api" },
              { label: "Set APP_ENCRYPTION_KEY in the API environment" },
              { label: "Restart the API once — existing keys stay readable if the old key is kept" },
            ]}
          />
        </div>
      )}

      <div className="mt-6">
        <MetricStrip
          metrics={[
            { label: "registered", value: String(providers.length), caption: "adapters" },
            { label: "ready", value: String(ready.length), caption: "with credentials", accent: ready.length > 0 },
            { label: "mock", value: String(mocks.length), caption: "development only" },
            { label: "unhealthy", value: String(errors.length), caption: "check required", accent: errors.length > 0 },
            { label: "vault", value: encryption.ready ? "aes-256-gcm" : "missing", caption: "authenticated encryption", accent: !encryption.ready },
            { label: "storage", value: integrations.storage_backend, caption: "asset backend" },
            { label: "renderer", value: integrations.ffmpeg_available ? "ffmpeg" : "missing", caption: "video engine" },
            { label: "oauth", value: integrations.google_oauth_configured ? "configured" : "unset", caption: "google" },
          ]}
        />
      </div>

      <div className="mt-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-2 border border-border bg-paper px-3 py-2 text-[12px] text-muted-foreground">
          <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-ink" />
          <span className="max-w-[64ch]">
            Precedence: an agent uses its bound provider; otherwise the first enabled real provider with a
            credential; mock adapters only fill in when nothing real is configured.{" "}
            {canManage
              ? "Add, rotate or remove keys inline — changes apply without a restart."
              : "You can inspect configuration; only admins can change credentials."}
          </span>
        </div>
        {canManage && <AddProvider existing={providers} />}
      </div>

      <Section>
        <SectionTitle title="Language models" index="01" caption="llm" />
        <ProviderSections groups={[{ key: "llm", rows: providers.filter((p) => p.kind === "llm") }]} canManage={canManage} />
      </Section>

      <Section>
        <SectionTitle title="Text to speech" index="02" caption="tts · cartesia · elevenlabs" />
        <ProviderSections groups={[{ key: "tts", rows: providers.filter((p) => p.kind === "tts") }]} canManage={canManage} />
        <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
          Try voices side by side in{" "}
          <a className="text-ink underline underline-offset-4" href="/studio/audio">
            Audio Studio
          </a>
          . Generation, latency and cost per provider are recorded under usage.
        </p>
      </Section>

      <Section>
        <SectionTitle title="Image generation" index="03" caption="image" />
        <ProviderSections groups={[{ key: "image", rows: providers.filter((p) => p.kind === "image") }]} canManage={canManage} />
      </Section>

      <Section>
        <SectionTitle title="YouTube delivery" index="04" caption="publishing" />
        {!integrations.google_oauth_configured && (
          <SetupState
            className="mb-3"
            title="Google OAuth is not configured"
            description="Publishing and analytics require a Google Cloud OAuth client with YouTube Data API v3 and YouTube Analytics API enabled. Add the client id and secret to the API server environment, then connect each channel."
            steps={[
              { label: "Create an OAuth client (Web application) in Google Cloud Console" },
              { label: "Enable YouTube Data API v3 and YouTube Analytics API" },
              { label: `Add redirect URI ${process.env.NEXT_PUBLIC_GOOGLE_REDIRECT ?? "http://localhost:8000/api/v1/youtube/callback"}` },
              { label: "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the API environment" },
            ]}
            action={{ label: "Open channels to connect", href: "/channels" }}
          />
        )}
        <ProviderSections groups={[{ key: "youtube", rows: providers.filter((p) => p.kind === "youtube") }]} canManage={canManage} />
      </Section>

      <Section className="pb-8">
        <SectionTitle title="Credential policy" index="05" caption="how secrets are handled" />
        <ul className="grid gap-2 text-[12.5px] text-muted-foreground md:grid-cols-2">
          {[
            ["AES-256-GCM at rest", "Each record is sealed with a unique 96-bit nonce and authenticated with the provider id, so a ciphertext cannot be moved to another row. APP_ENCRYPTION_KEY never enters the database."],
            ["Never serialized", "Responses expose only a one-way fingerprint (sk-…a91f), a status and a version. No endpoint returns a key, and provider error text is redacted."],
            ["Server-side only", "Adapters decrypt inside the API process. The browser only ever receives generated audio."],
            ["Rotatable without restart", "Writes bump credential_version and refresh the in-process cache immediately. Running workflows pin the version they started with."],
            ["Auditable", "Every create, rotate, remove and connection test is written to the audit log with field names and fingerprints — never values."],
            ["Graceful failures", "A rejected key marks the provider unhealthy and surfaces the provider's message; production never invents audio."],
          ].map(([title, body]) => (
            <li key={title} className="flex gap-2 border border-border px-3 py-2">
              <KeyRound className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
              <span>
                <span className="block text-ink">{title}</span>
                {body}
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}
