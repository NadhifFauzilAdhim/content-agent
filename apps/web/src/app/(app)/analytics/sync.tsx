"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { buttonStyles } from "@/components/ui/button";

export function SyncAnalytics({ disabled }: { disabled: boolean }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  return (
    <button
      type="button"
      disabled={pending || disabled}
      onClick={async () => {
        setPending(true);
        try {
          const res = await fetch("/api/proxy/analytics/sync", { method: "POST" });
          const data = await res.json();
          if (!res.ok) throw new Error(data?.error?.message ?? "Sync failed");
          toast.success(`Collected ${data.snapshots} snapshots`, { description: `${data.channels} channel(s)` });
          router.refresh();
        } catch (err) {
          toast.error("Analytics sync failed", { description: (err as Error).message });
        } finally {
          setPending(false);
        }
      }}
      className={buttonStyles("primary", "md")}
    >
      {pending ? <Loader2 className="animate-spin !size-3" /> : <RefreshCw className="!size-3" />} sync from youtube
    </button>
  );
}
