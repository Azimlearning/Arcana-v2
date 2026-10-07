"use client";

// The labs screen (P4, D-36): ask the server for a lab and show it. A lab is made on request (the server generates, checks and verifies it,
// or says at which stage it failed) and shown through the block registry like every other block; this screen never inspects the block, and
// the code in it can only run inside the registry's sandboxed iframe.

import type { ErrorEnvelope, UIBlock } from "@arcana/schema";
import Link from "next/link";
import { useState } from "react";

import { renderBlock } from "@/components/genui/registry";
import { makeLab } from "@/lib/api";

type State = { state: "idle" } | { state: "making" } | { state: "error"; error: ErrorEnvelope } | { state: "ready"; blocks: UIBlock[] };

export const LABS = [{ id: "ranknet_pairwise_loss", label: "RankNet pairwise loss" }] as const;

export function LabsScreen() {
  const [view, setView] = useState<State>({ state: "idle" });

  const make = async (contractId: string) => {
    setView({ state: "making" });
    const result = await makeLab(contractId);
    setView(result.ok ? { state: "ready", blocks: result.workspace.blocks } : { state: "error", error: result.error });
  };

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="flex items-center gap-4 border-b border-stone-200 bg-white px-6 py-3">
        <span className="text-lg font-semibold">Arcana</span>
        <nav aria-label="Views" className="flex gap-3 text-sm">
          <Link href="/" className="text-stone-600 hover:text-stone-900">
            Chat
          </Link>
          <Link href="/notes" className="text-stone-600 hover:text-stone-900">
            Notes
          </Link>
          <Link href="/labs" aria-current="page" className="font-medium text-stone-900 underline underline-offset-4">
            Labs
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-3xl space-y-4 p-6">
        <h1 className="text-xl font-semibold">Labs</h1>
        <p className="text-sm text-stone-600">
          A lab is an interactive plot of a formula your documents state. The function is written for the formula and is shown only after the server has checked it
          with rules that allow only arithmetic and verified it against reference cases.
        </p>
        <div className="flex flex-wrap gap-2">
          {LABS.map((lab) => (
            <button
              key={lab.id}
              type="button"
              aria-disabled={view.state === "making"}
              onClick={() => {
                if (view.state !== "making") void make(lab.id);
              }}
              className="rounded-lg bg-stone-900 px-3 py-1.5 text-sm text-white"
            >
              Make the {lab.label} lab
            </button>
          ))}
        </div>
        {view.state === "making" && (
          <p role="status" aria-busy="true" className="text-sm text-stone-500">
            Making and checking the lab…
          </p>
        )}
        {view.state === "error" && (
          <p role="alert" className="text-sm text-red-700">
            {view.error.message}
          </p>
        )}
        {view.state === "ready" && view.blocks.map((block) => <div key={block.id}>{renderBlock(block)}</div>)}
      </main>
    </div>
  );
}
