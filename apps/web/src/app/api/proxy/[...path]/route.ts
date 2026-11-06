import { type NextRequest, NextResponse } from "next/server";

const API = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

/**
 * Authenticated same-origin proxy to the Factory API. Mutations from client components call
 * `/api/proxy/<path>`; the API session cookie never reaches browser JavaScript.
 */
async function forward(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const token = request.cookies.get("factory_session")?.value;
  const url = new URL(`${API}/api/v1/${path.join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value));

  const method = request.method;
  const body = method === "GET" || method === "DELETE" ? undefined : await request.text();
  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method,
      headers: {
        "content-type": "application/json",
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
      body,
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { error: { code: "api_unreachable", message: "The Factory API is unreachable." } },
      { status: 503 },
    );
  }
  if (upstream.status === 204) return new NextResponse(null, { status: 204 });
  if (path[0] === "files" && upstream.ok) {
    // Stream binary assets (scene images, audio, renders) without buffering through JSON.
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/octet-stream",
        "cache-control": "private, max-age=300",
      },
    });
  }
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const PUT = forward;
export const DELETE = forward;
