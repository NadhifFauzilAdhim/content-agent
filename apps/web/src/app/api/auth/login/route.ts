import { NextResponse } from "next/server";

const API = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  if (!body?.email || !body?.password) {
    return NextResponse.json(
      { error: { code: "validation_error", message: "Email and password are required." } },
      { status: 422 },
    );
  }
  let upstream: Response;
  try {
    upstream = await fetch(`${API}/api/v1/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: body.email, password: body.password }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      {
        error: {
          code: "api_unreachable",
          message: "The API is not reachable. Start it with `uvicorn app.main:app --port 8000`.",
        },
      },
      { status: 502 },
    );
  }
  const data = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return NextResponse.json(
      { error: data.error ?? { code: "login_failed", message: "Sign-in failed" } },
      { status: upstream.status },
    );
  }
  const setCookie = upstream.headers.get("set-cookie");
  const res = NextResponse.json({ user: data.user, workspace: data.workspace });
  if (setCookie) {
    res.headers.append("set-cookie", setCookie);
  }
  return res;
}
