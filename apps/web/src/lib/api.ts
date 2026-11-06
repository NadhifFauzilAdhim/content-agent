import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import type {
  Agent,
  Analytics,
  ApiKey,
  Approval,
  AuditLog,
  Channel,
  Costs,
  IntegrationConfig,
  Member,
  Overview,
  Project,
  ProjectDetail,
  Provider,
  Schedule,
  Session,
  SystemStatus,
  TTSProviderRow,
  Workflow,
  WorkflowDetail,
} from "./types";

/**
 * Server-only API client. The browser never talks to FastAPI directly: every request is made from
 * the Next.js server, forwarding the httpOnly session cookie. Provider credentials never leave the API.
 */

export const COOKIE_NAME = "factory_session";

function apiBase(): string {
  return process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
}

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type ApiOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  token?: string | null;
  query?: Record<string, string | number | boolean | undefined | null>;
};

export async function sessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(COOKIE_NAME)?.value ?? null;
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const token = options.token ?? (await sessionToken());
  const url = new URL(`${apiBase()}/api/v1${path}`);
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  let res: Response;
  try {
    res = await fetch(url, {
      method: options.method ?? "GET",
      headers: {
        "content-type": "application/json",
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(503, "api_unreachable", "The Factory API is unreachable. Is it running on port 8000?");
  }
  if (!res.ok) {
    let code = "http_error";
    let message = `Request failed (${res.status})`;
    let details: unknown;
    try {
      const data = await res.json();
      if (data?.error) {
        code = data.error.code;
        message = data.error.message;
        details = data.error.details;
      } else if (data?.detail) {
        message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      /* non-JSON */
    }
    throw new ApiError(res.status, code, message, details);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return err instanceof Error ? err.message : "Unknown error";
}

/** Fetch for server components: redirects unauthenticated sessions to /login. */
export async function apiPage<T>(path: string, options: ApiOptions = {}): Promise<T> {
  try {
    return await api<T>(path, options);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) redirect("/login");
    throw err;
  }
}

/** Fetch that degrades to a fallback so one broken panel doesn't blank the page. */
export async function apiSafe<T>(path: string, fallback: T, options: ApiOptions = {}): Promise<T> {
  try {
    return await api<T>(path, options);
  } catch {
    return fallback;
  }
}

export async function getSession(): Promise<Session | null> {
  const token = await sessionToken();
  if (!token) return null;
  try {
    return await api<Session>("/auth/session", { token });
  } catch {
    return null;
  }
}

export async function requireSession(): Promise<Session> {
  const session = await getSession();
  if (!session) redirect("/login");
  return session;
}

export const resources = {
  overview: () => apiPage<Overview>("/overview"),
  session: () => apiPage<Session>("/auth/session"),
  ttsProviders: () => apiPage<TTSProviderRow[]>("/tts/providers"),
  systemStatus: () => apiPage<SystemStatus>("/system/status"),
  integrations: () => apiPage<IntegrationConfig>("/system/integrations"),
  channels: () => apiPage<Channel[]>("/channels"),
  channel: (id: string) => apiPage<Channel>(`/channels/${id}`),
  schedules: (id: string) => apiPage<Schedule[]>(`/channels/${id}/schedules`),
  youtube: () => apiPage<{ oauth_configured: boolean; connections: unknown[] }>("/youtube/status"),
  projects: (query: Record<string, string> = {}) => apiPage<Project[]>("/content", { query }),
  project: (id: string) => apiPage<ProjectDetail>(`/content/${id}`),
  workflows: (query: Record<string, string> = {}) => apiPage<Workflow[]>("/workflows", { query }),
  workflow: (id: string) => apiPage<WorkflowDetail>(`/workflows/${id}`),
  agents: () => apiPage<Agent[]>("/agents"),
  providers: () => apiPage<Provider[]>("/providers"),
  approvals: (status = "pending") => apiPage<Approval[]>("/approvals", { query: { status } }),
  costs: () => apiPage<Costs>("/costs"),
  analytics: () => apiPage<Analytics>("/analytics"),
  members: () => apiPage<Member[]>("/workspace/members"),
  workspace: () =>
    apiPage<{ id: string; name: string; slug: string; plan: string; monthly_budget_usd: number | null; role: string }>(
      "/workspace",
    ),
  audit: () => apiPage<AuditLog[]>("/workspace/audit", { query: { limit: 80 } }),
  apiKeys: () => apiPage<ApiKey[]>("/workspace/api-keys"),
};

/** Storage URLs from the API are relative to the API origin; the browser fetches them via our proxy. */
export function assetUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  if (url.startsWith("/files/")) return `/api/proxy${url}`;
  return url;
}

export {
  formatBytes,
  formatCompact,
  formatDuration,
  formatNumber,
  formatUsd,
  formatWhen,
  relativeTime,
} from "./format";

export { errorMessage };