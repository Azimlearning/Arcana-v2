"use client";

// How a notes block asks the screen to open another page. A block carries data only (constraint 2), so it holds no behaviour:
// the notes screen provides `openPage` through this context and a page name renders as a button when it is there, and as plain
// text when it is not (a saved view, a test, any screen that has no notes view).

import type { LearnerSignal } from "@arcana/schema";
import { createContext, useContext } from "react";

export interface NotesNavValue {
  openPage: (id: string) => void;
  /** Record the learner's own rating of a page. Absent when the screen cannot (no buttons are drawn then). */
  rate?: (pageId: string, signal: LearnerSignal) => Promise<boolean>;
}

export const NotesNav = createContext<NotesNavValue | null>(null);

export function useNotesNav() {
  return useContext(NotesNav);
}

/** A page's name: a button that opens it when the screen can, plain text when it cannot. */
export function PageName({ id, label, current = false }: { id: string; label: string; current?: boolean }) {
  const nav = useNotesNav();
  if (!nav || current) return <span className={current ? "font-semibold" : undefined}>{label}</span>;
  return (
    <button
      type="button"
      onClick={() => nav.openPage(id)}
      className="rounded px-0.5 text-left font-medium text-emerald-800 underline decoration-emerald-300 underline-offset-2 hover:bg-emerald-50"
    >
      {label}
    </button>
  );
}
