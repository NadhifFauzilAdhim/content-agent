"use client";

/**
 * Thin browser client for the TTS endpoints. Every call goes through the authenticated same-origin
 * proxy (`/api/proxy/...`) so the session cookie never reaches JavaScript.
 */

export type ApiFailure = { code: string; message: string; status: number };

export class StudioError extends Error {
  code: string;
  status: number;
  constructor(failure: ApiFailure) {
    super(failure.message);
    this.code = failure.code;
    this.status = failure.status;
  }
}

async function parse<T>(res: Response): Promise<T> {
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const envelope = data as { error?: { code?: string; message?: string } } | null;
    throw new StudioError({
      code: envelope?.error?.code ?? `http_${res.status}`,
      message: envelope?.error?.message ?? `Request failed (${res.status})`,
      status: res.status,
    });
  }
  return data as T;
}

export async function studio<T>(
  path: string,
  init: { method?: "GET" | "POST" | "PUT" | "DELETE"; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const res = await fetch(`/api/proxy/tts/${path}`, {
    method: init.method ?? "GET",
    headers: init.body ? { "content-type": "application/json" } : undefined,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    cache: "no-store",
    signal: init.signal,
  });
  return parse<T>(res);
}

/** Provider endpoints that are not published by the generic proxy path (credentials). */
export async function providerCredentials(
  kind: string,
  slug: string,
  init: { method?: "POST" | "PUT" | "DELETE"; body?: unknown } = {},
) {
  const res = await fetch(`/api/proxy/providers/${kind}/${slug}/credentials`, {
    method: init.method ?? "POST",
    headers: init.body ? { "content-type": "application/json" } : undefined,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    cache: "no-store",
  });
  return parse<{
    provider: string;
    kind: string;
    has_credential: boolean;
    status: string;
    version: number;
    fingerprint: string | null;
    updated_at: string | null;
    fields: string[];
    readable: boolean;
    problem: string | null;
    encryption_ready: boolean;
  }>(res);
}

export function previewUrl(endpoint: string | null): string | undefined {
  if (!endpoint) return undefined;
  // preview_endpoint is "/api/v1/tts/voices/<provider>/<voice>/preview"
  return `/api/proxy/${endpoint.replace(/^\/api\/v1\//, "")}`;
}

export function audioUrl(url: string | null): string | undefined {
  if (!url) return undefined;
  if (url.startsWith("/files/")) return `/api/proxy${url}`;
  return url;
}
