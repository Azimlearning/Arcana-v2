// The Studio area (D-32, D-42): the learning and writing tools a learner uses to turn their documents into study material, and
// below them the outputs shelf. Each tool is a starter, not a generator of its own: it puts a request in the question box (or
// asks it at once), and the Orchestrator's `write` and `study` intents route it to the Studio agent. So the shelf holds no
// behaviour the server does not have, and nothing here calls the server directly.

export interface StudioStarter {
  id: string;
  label: string;
  hint: string;
  /** The request put in the question box. */
  request: string;
  /** True when the request is complete and is asked at once; false when the learner adds a topic first. */
  submit: boolean;
}

/** The tools the Studio agent has, in the order they are shown. Each request opens with the words the server recognises. */
export const STARTERS: readonly StudioStarter[] = [
  { id: "quiz", label: "Quiz me", hint: "Fill the blank", request: "Quiz me on ", submit: false },
  { id: "flashcards", label: "Flashcards", hint: "Name a topic", request: "Make flashcards for ", submit: false },
  { id: "blurt", label: "Blurting", hint: "Recall, then check", request: "Make a blurting exercise for ", submit: false },
  { id: "cornell", label: "Cornell notes", hint: "Name a topic", request: "Give me cornell notes on ", submit: false },
  { id: "socratic", label: "Socratic questions", hint: "Name a topic", request: "Guide me with socratic questions about ", submit: false },
  { id: "review", label: "Review schedule", hint: "What is due", request: "What should I review today?", submit: true },
  { id: "write", label: "Write an outline", hint: "Name a topic", request: "Write an outline on ", submit: false },
  { id: "litreview", label: "Literature review", hint: "Cited, by theme", request: "Write a literature review of ", submit: false },
  { id: "abstract", label: "Abstract", hint: "Cited, short", request: "Write an abstract on ", submit: false },
  { id: "audio", label: "Audio overview", hint: "A script to listen to", request: "Make an audio overview of ", submit: false },
];

export function Studio({ onStart }: { onStart?: (request: string, submit: boolean) => void }) {
  return (
    <section aria-label="Studio" className="space-y-2">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">Studio</h2>
      <ul className="grid grid-cols-2 gap-2 text-sm">
        {STARTERS.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              disabled={!onStart}
              onClick={() => onStart?.(s.request, s.submit)}
              className="h-full w-full rounded-lg border border-stone-300 bg-white p-2 text-left hover:border-stone-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span className="block font-medium text-stone-800">{s.label}</span>
              <span className="block text-xs text-stone-500">{s.hint}</span>
            </button>
          </li>
        ))}
        <li>
          <a
            href="/notes"
            className="block h-full rounded-lg border border-stone-300 bg-white p-2 hover:border-stone-500"
          >
            <span className="block font-medium text-stone-800">Notes</span>
            <span className="block text-xs text-stone-500">Pages, graph, quiz</span>
          </a>
        </li>
      </ul>
    </section>
  );
}
