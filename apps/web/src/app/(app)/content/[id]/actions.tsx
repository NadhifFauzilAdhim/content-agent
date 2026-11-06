"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ImageIcon, Loader2, Mic, Pencil, X } from "lucide-react";
import { toast } from "sonner";

import { buttonStyles } from "@/components/ui/button";

async function send(path: string, method: string, body?: unknown) {
  const res = await fetch(`/api/proxy${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error?.message ?? `Request failed (${res.status})`);
  return data;
}

export function SceneRegenerate({
  projectId,
  sceneIndex,
  target,
  hasAsset,
}: {
  projectId: string;
  sceneIndex: number;
  target: "image" | "audio";
  hasAsset: boolean;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  return (
    <button
      type="button"
      disabled={pending}
      onClick={async () => {
        setPending(true);
        try {
          await send(`/content/${projectId}/scenes/${sceneIndex}/regenerate?target=${target}`, "POST");
          toast.success(`Scene ${sceneIndex} ${target} regenerated`);
          router.refresh();
        } catch (err) {
          toast.error("Regeneration failed", { description: (err as Error).message });
        } finally {
          setPending(false);
        }
      }}
      className={buttonStyles("ghost", "xs")}
      title={hasAsset ? `Regenerate the scene ${target}` : `Generate the scene ${target}`}
    >
      {pending ? (
        <Loader2 className="animate-spin !size-2.5" />
      ) : target === "image" ? (
        <ImageIcon className="!size-2.5" />
      ) : (
        <Mic className="!size-2.5" />
      )}
      {hasAsset ? "regen" : "generate"} {target}
    </button>
  );
}

export function MetadataEditor({
  projectId,
  seo,
}: {
  projectId: string;
  seo: { title?: string; description?: string; tags?: string[]; thumbnail_text?: string; playlist?: string };
}) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(seo.title ?? "");
  const [description, setDescription] = useState(seo.description ?? "");
  const [tags, setTags] = useState((seo.tags ?? []).join(", "));
  const [pending, setPending] = useState(false);

  if (!editing) {
    return (
      <button type="button" className={buttonStyles("outline", "xs")} onClick={() => setEditing(true)}>
        <Pencil className="!size-2.5" /> edit metadata
      </button>
    );
  }

  return (
    <div className="w-full border border-ink bg-white p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="mono-label text-ink">edit metadata</span>
        <button type="button" onClick={() => setEditing(false)} className="text-muted-foreground hover:text-ink" aria-label="Cancel">
          <X className="size-3.5" />
        </button>
      </div>
      <label className="mono-label mb-1 block">title</label>
      <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={240} className="mb-2 h-8 w-full border border-border px-2 text-[13px] outline-none focus:border-ink" />
      <label className="mono-label mb-1 block">description</label>
      <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4} className="mb-2 w-full border border-border px-2 py-1.5 text-[12.5px] outline-none focus:border-ink" />
      <label className="mono-label mb-1 block">tags · comma separated</label>
      <input value={tags} onChange={(e) => setTags(e.target.value)} className="mb-3 h-8 w-full border border-border px-2 font-mono text-[11.5px] outline-none focus:border-ink" />
      <div className="flex justify-end gap-2">
        <button type="button" className={buttonStyles("ghost", "sm")} onClick={() => setEditing(false)}>cancel</button>
        <button
          type="button"
          disabled={pending}
          className={buttonStyles("primary", "sm")}
          onClick={async () => {
            setPending(true);
            try {
              const current = { ...seo, title, description, tags: tags.split(",").map((t) => t.trim()).filter(Boolean) };
              await send(`/content/${projectId}`, "PATCH", { title, seo: current });
              toast.success("Metadata saved");
              setEditing(false);
              router.refresh();
            } catch (err) {
              toast.error("Could not save", { description: (err as Error).message });
            } finally {
              setPending(false);
            }
          }}
        >
          {pending && <Loader2 className="animate-spin !size-3" />} save
        </button>
      </div>
    </div>
  );
}

export function ApprovalDecision({ approvalId, projectId }: { approvalId: string; projectId: string }) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [pending, setPending] = useState<"approve" | "reject" | null>(null);

  async function decide(decision: "approve" | "reject") {
    setPending(decision);
    try {
      await send(`/approvals/${approvalId}/decision`, "POST", { decision, note: note || undefined });
      toast.success(decision === "approve" ? "Approved — publishing queued" : "Rejected");
      router.refresh();
    } catch (err) {
      toast.error("Decision failed", { description: (err as Error).message });
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="border border-ink bg-white">
      <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
        <span className="mono-label text-ink">decision</span>
        <span className="mono-label text-subtle">{projectId.slice(0, 8)}</span>
      </div>
      <div className="p-3">
        <label htmlFor="note" className="mono-label mb-1 block">reviewer note</label>
        <textarea
          id="note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          placeholder="optional — recorded in the audit log"
          className="w-full border border-border px-2 py-1.5 text-[12.5px] outline-none focus:border-ink"
        />
        <div className="mt-2 grid grid-cols-2 gap-2">
          <button type="button" disabled={pending !== null} onClick={() => decide("reject")} className={buttonStyles("secondary", "md")}>
            {pending === "reject" && <Loader2 className="animate-spin !size-3" />} reject
          </button>
          <button type="button" disabled={pending !== null} onClick={() => decide("approve")} className={buttonStyles("accent", "md")}>
            {pending === "approve" && <Loader2 className="animate-spin !size-3" />} approve
          </button>
        </div>
        <p className="mt-2 font-mono text-[9.5px] uppercase leading-relaxed tracking-wider text-subtle">
          approval unlocks publishing to the connected YouTube channel
        </p>
      </div>
    </div>
  );
}
