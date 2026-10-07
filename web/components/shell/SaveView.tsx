"use client";

// "Save this view": keep one view of the answer (a graph, a comparison, a path) to show again later. The server decides
// whether it can be saved and says why if not; this only collects a name.

import { useState } from "react";

export type SaveOutcome = { ok: true } | { ok: false; message: string };

export function SaveView({
  defaultName,
  onSave,
}: {
  defaultName: string;
  onSave: (name: string) => Promise<SaveOutcome>;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(defaultName);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<SaveOutcome | null>(null);

  if (outcome?.ok) {
    return (
      <p role="status" className="mt-2 text-xs text-emerald-700">
        Saved. You will find it on the Studio shelf, under Saved views.
      </p>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-2 rounded border border-stone-300 px-2 py-0.5 text-xs text-stone-700 hover:bg-stone-100"
      >
        Save this view
      </button>
    );
  }

  return (
    <form
      className="mt-2 flex flex-wrap items-center gap-2 text-xs"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setOutcome(await onSave(name));
        setBusy(false);
      }}
    >
      <label className="flex items-center gap-1">
        <span className="text-stone-600">Name</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={80}
          className="rounded border border-stone-300 px-2 py-0.5 text-stone-900"
        />
      </label>
      <button type="submit" disabled={busy || !name.trim()} className="rounded bg-stone-900 px-2 py-0.5 text-white disabled:opacity-40">
        Save
      </button>
      <button type="button" onClick={() => setOpen(false)} className="rounded border border-stone-300 px-2 py-0.5">
        Cancel
      </button>
      {outcome && !outcome.ok && (
        <span role="alert" className="basis-full text-red-700">
          {outcome.message}
        </span>
      )}
    </form>
  );
}
