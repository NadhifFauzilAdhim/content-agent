"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, Loader2, Plus, UserPlus } from "lucide-react";
import { toast } from "sonner";

import type { ApiKey } from "@/lib/types";
import { buttonStyles } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";

export function ChangePassword() {
  const [form, setForm] = useState({ current: "", next: "" });
  const [pending, setPending] = useState(false);
  return (
    <form
      className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
      onSubmit={async (e) => {
        e.preventDefault();
        setPending(true);
        try {
          const res = await fetch("/api/proxy/auth/password", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ current_password: form.current, new_password: form.next }),
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data?.error?.message ?? "Update failed");
          toast.success("Password updated");
          setForm({ current: "", next: "" });
        } catch (err) {
          toast.error("Could not change password", { description: (err as Error).message });
        } finally {
          setPending(false);
        }
      }}
    >
      <Field label="current password"><Input type="password" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} autoComplete="current-password" /></Field>
      <Field label="new password" hint="minimum 10 characters"><Input type="password" minLength={10} value={form.next} onChange={(e) => setForm({ ...form, next: e.target.value })} autoComplete="new-password" /></Field>
      <button type="submit" disabled={pending || !form.current || form.next.length < 10} className={buttonStyles("primary", "md")}>
        {pending && <Loader2 className="animate-spin !size-3" />} update
      </button>
    </form>
  );
}

export function InviteMember() {
  const router = useRouter();
  const [form, setForm] = useState({ email: "", name: "", role: "editor", password: "" });
  const [pending, setPending] = useState(false);
  return (
    <form
      className="grid gap-3 md:grid-cols-[1.2fr_1fr_0.8fr_1fr_auto] md:items-end"
      onSubmit={async (e) => {
        e.preventDefault();
        setPending(true);
        try {
          const res = await fetch("/api/proxy/workspace/members", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ ...form, password: form.password || null }),
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data?.error?.message ?? "Invite failed");
          toast.success("Member added");
          setForm({ email: "", name: "", role: "editor", password: "" });
          router.refresh();
        } catch (err) {
          toast.error("Could not add member", { description: (err as Error).message });
        } finally {
          setPending(false);
        }
      }}
    >
      <Field label="email"><Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
      <Field label="name"><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
      <Field label="role">
        <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          <option value="editor">editor</option>
          <option value="admin">admin</option>
          <option value="viewer">viewer</option>
        </Select>
      </Field>
      <Field label="initial password" hint="new users only"><Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
      <button type="submit" disabled={pending} className={buttonStyles("primary", "md")}>
        {pending ? <Loader2 className="animate-spin !size-3" /> : <UserPlus className="!size-3" />} add
      </button>
    </form>
  );
}

export function ApiKeyManager({ keys }: { keys: ApiKey[] }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  return (
    <div className="space-y-3">
      <div className="flex items-end gap-2">
        <Field label="key name" className="flex-1"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="ci-pipeline" /></Field>
        <button
          type="button"
          disabled={pending || name.length < 2}
          onClick={async () => {
            setPending(true);
            try {
              const res = await fetch("/api/proxy/workspace/api-keys", {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ name }),
              });
              const data = await res.json();
              if (!res.ok) throw new Error(data?.error?.message ?? "Could not create key");
              setCreated(data.token);
              setName("");
              router.refresh();
            } catch (err) {
              toast.error("Could not create key", { description: (err as Error).message });
            } finally {
              setPending(false);
            }
          }}
          className={buttonStyles("primary", "md")}
        >
          <Plus className="!size-3" /> create key
        </button>
      </div>
      {created && (
        <div className="border border-ink bg-accent-soft px-3 py-2">
          <p className="mono-label text-ink">copy now — shown once</p>
          <code className="mt-1 block break-all font-mono text-[11px]">{created}</code>
          <button type="button" onClick={() => { navigator.clipboard?.writeText(created); toast.success("Copied"); }} className={buttonStyles("outline", "xs", "mt-2")}>
            copy
          </button>
        </div>
      )}
      <ul className="divide-y divide-border border-y border-border">
        {keys.map((k) => (
          <li key={k.id} className="flex items-center justify-between gap-2 py-2">
            <span className="flex items-center gap-2">
              <KeyRound className="size-3 text-muted-foreground" />
              <span className="text-[12.5px]">{k.name}</span>
              <code className="font-mono text-[10px] text-muted-foreground">{k.prefix}…</code>
            </span>
            <button
              type="button"
              className={buttonStyles("ghost", "xs")}
              onClick={async () => {
                const res = await fetch(`/api/proxy/workspace/api-keys/${k.id}`, { method: "DELETE" });
                if (res.ok) {
                  toast.success("Key revoked");
                  router.refresh();
                } else toast.error("Could not revoke key");
              }}
            >
              revoke
            </button>
          </li>
        ))}
        {keys.length === 0 && <li className="py-2 text-[12.5px] text-muted-foreground">No machine keys.</li>}
      </ul>
    </div>
  );
}
