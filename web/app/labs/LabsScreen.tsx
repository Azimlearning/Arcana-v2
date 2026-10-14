"use client";

// The labs screen (P4, D-36): the labs your documents support, and a lab made from one of them. The server lists every lab it can make and
// says, for each, whether a stored passage states its formula (constraint 7: a lab is offered only where the documents support it); asking
// for one makes it (the server generates, checks and verifies it, or says at which stage it failed) and it is shown through the block
// registry like every other block. This screen never inspects a block, and the code in it can only run inside the registry's sandboxed iframe.

import type { ErrorEnvelope, LabSummary, UIBlock } from "@arcana/schema";
import Link from "next/link";
import { useEffect, useState } from "react";

import { renderBlock } from "@/components/genui/registry";
import { fetchLabs, makeLab } from "@/lib/api";

type List = { state: "loading" } | { state: "error"; error: ErrorEnvelope } | { state: "ready"; labs: LabSummary[] };
type Made = { state: "idle" } | { state: "making"; id: string } | { state: "error"; error: ErrorEnvelope } | { state: "ready"; blocks: UIBlock[] };

export function LabsScreen() {
  const [list, setList] = useState<List>({ state: "loading" });
  const [made, setMade] = useState<Made>({ state: "idle" });

  useEffect(() => {
    const abort = new AbortController();
    void fetchLabs({ signal: abort.signal }).then((result) => {
      if (abort.signal.aborted) return;
      setList(result.ok ? { state: "ready", labs: result.labs } : { state: "error", error: result.error });
    });
    return () => abort.abort();
  }, []);

  const make = async (contractId: string) => {
    setMade({ state: "making", id: contractId });
    const result = await makeLab(contractId);
    setMade(result.ok ? { state: "ready", blocks: result.workspace.blocks } : { state: "error", error: result.error });
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
          A lab is an interactive plot of a formula your documents state. It is offered only where a stored passage states the formula, and its
          function is shown only after the server has checked it with rules that allow only arithmetic and verified it on every setting the sliders
          can reach.
        </p>
        {list.state === "loading" && (
          <p role="status" aria-busy="true" className="text-sm text-stone-500">
            Looking at which formulas your documents state…
          </p>
        )}
        {list.state === "error" && (
          <p role="alert" className="text-sm text-red-700">
            {list.error.message}
          </p>
        )}
        {list.state === "ready" && (
          <ul aria-label="Available labs" className="space-y-2">
            {list.labs.map((lab) => (
              <li key={lab.contractId} className="rounded-lg border border-stone-200 bg-white p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-stone-900">{lab.title}</p>
                    <p className="text-xs text-stone-500">
                      {lab.available
                        ? `Stated in ${lab.docTitle ?? "a stored document"}${lab.page != null ? ` · page ${lab.page}` : ""}`
                        : (lab.reason ?? "Not supported by your documents.")}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={!lab.available || made.state === "making"}
                    onClick={() => void make(lab.contractId)}
                    className="rounded-lg bg-stone-900 px-3 py-1.5 text-sm text-white disabled:cursor-not-allowed disabled:bg-stone-300"
                  >
                    Make this lab
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {made.state === "making" && (
          <p role="status" aria-busy="true" className="text-sm text-stone-500">
            Making and checking the lab…
          </p>
        )}
        {made.state === "error" && (
          <p role="alert" className="text-sm text-red-700">
            {made.error.message}
          </p>
        )}
        {made.state === "ready" && made.blocks.map((block) => <div key={block.id}>{renderBlock(block)}</div>)}
      </main>
    </div>
  );
}
