import { redirect } from "next/navigation";
import type { Metadata } from "next";

import { getSession } from "@/lib/api";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage() {
  const session = await getSession();
  if (session) redirect("/");

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.15fr_1fr]">
      {/* editorial side */}
      <div className="relative hidden flex-col justify-between border-r border-ink bg-white p-10 lg:flex">
        <div className="dot-grid pointer-events-none absolute inset-0 opacity-60" aria-hidden />
        <div className="relative flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="grid size-4 place-items-center bg-ink">
              <span className="size-1.5 bg-accent" />
            </span>
            <span className="text-[17px] font-semibold tracking-[-0.02em]">
              factory<span className="text-muted-foreground">/</span>ai
            </span>
          </div>
          <span className="bg-accent px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em]">
            autonomous studio
          </span>
        </div>

        <div className="relative max-w-[560px]">
          <p className="mono-label text-ink">fig. 01 — production loop</p>
          <h1 className="editorial-title mt-4 text-[64px] leading-[0.92]">
            Ten agents.
            <br />
            One <em className="italic">factory</em>
            <br />
            for stories.
          </h1>
          <p className="mt-5 max-w-[46ch] text-[14px] leading-relaxed text-muted-foreground">
            Plan, write, storyboard, voice, illustrate, render, review and publish original children&apos;s
            videos on a schedule — with a human in the loop before anything goes live.
          </p>
          <ol className="mt-8 grid grid-cols-2 gap-x-8 border-t border-ink">
            {[
              ["01", "Content planner"],
              ["02", "Script writer"],
              ["03", "Storyboard"],
              ["04", "Voice"],
              ["05", "Visuals"],
              ["06", "Render"],
              ["07", "Quality control"],
              ["08", "SEO"],
              ["09", "Approval"],
              ["10", "Publish"],
            ].map(([n, l]) => (
              <li key={n} className="flex items-baseline gap-3 border-b border-border py-1.5">
                <span className="font-mono text-[10px] text-subtle">{n}</span>
                <span className="text-[12.5px]">{l}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="relative flex items-center justify-between font-mono text-[9.5px] uppercase tracking-[0.14em] text-subtle">
          <span>multi-channel · multi-provider · temporal-ready</span>
          <span>v0.1</span>
        </div>
      </div>

      {/* form side */}
      <div className="flex flex-col justify-center bg-paper px-6 py-12 sm:px-12">
        <div className="mx-auto w-full max-w-[360px]">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <span className="grid size-4 place-items-center bg-ink">
              <span className="size-1.5 bg-accent" />
            </span>
            <span className="text-[17px] font-semibold tracking-[-0.02em]">factory/ai</span>
          </div>
          <p className="mono-label text-ink">operator access</p>
          <h2 className="editorial-title mt-2 text-[40px]">Sign in</h2>
          <p className="mt-2 mb-8 text-[13px] leading-relaxed text-muted-foreground">
            Authenticate to reach the production control room.
          </p>
          <LoginForm />
        </div>
      </div>
    </div>
  );
}
