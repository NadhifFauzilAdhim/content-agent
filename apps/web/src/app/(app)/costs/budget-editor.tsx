"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Save } from "lucide-react";
import { toast } from "sonner";

import { buttonStyles } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function BudgetEditor({ monthly, channelCeiling }: { monthly: number | null; channelCeiling: number | null }) {
  const router = useRouter();
  const [values, setValues] = useState({ monthly: monthly ?? 250, channelCeiling: channelCeiling ?? 4.5 });
  const [pending, setPending] = useState(false);

  async function save() {
    setPending(true);
    try {
      const res = await fetch("/api/proxy/costs/budget", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ monthly_budget_usd: values.monthly, channel_ceiling_usd: values.channelCeiling }),
      });
      if (!res.ok) throw new Error((await res.json())?.error?.message ?? "Update failed");
      toast.success("Budgets saved", { description: "Productions stop when the monthly budget is reached." });
      router.refresh();
    } catch (err) {
      toast.error("Could not save budget", { description: (err as Error).message });
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
      <label className="block">
        <span className="mono-label mb-1 block text-ink">monthly workspace budget · usd</span>
        <Input type="number" min={0} step={10} value={values.monthly} onChange={(e) => setValues({ ...values, monthly: Number(e.target.value) })} />
      </label>
      <label className="block">
        <span className="mono-label mb-1 block text-ink">per-video ceiling · usd</span>
        <Input type="number" min={0} step={0.1} value={values.channelCeiling} onChange={(e) => setValues({ ...values, channelCeiling: Number(e.target.value) })} />
      </label>
      <button type="button" disabled={pending} onClick={save} className={buttonStyles("primary", "md")}>
        {pending ? <Loader2 className="animate-spin !size-3" /> : <Save className="!size-3" />} save
      </button>
    </div>
  );
}
