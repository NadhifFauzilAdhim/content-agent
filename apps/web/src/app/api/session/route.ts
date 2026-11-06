import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const API = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export async function DELETE() {
  const store = await cookies();
  const token = store.get("factory_session")?.value;
  if (token) {
    await fetch(`${API}/api/v1/auth/logout`, {
      method: "POST",
      headers: { authorization: `Bearer ${token}` },
    }).catch(() => undefined);
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.delete("factory_session");
  return res;
}
