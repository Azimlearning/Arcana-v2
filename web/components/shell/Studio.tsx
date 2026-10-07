// The Studio area (D-32): the generators a learner will use to turn their documents into study material, and below them
// the outputs shelf. In P2b it is a shell. The generators do not exist yet (they are the Studio agent's work, P5), so each
// one is drawn inert and says so: it is a list item, not a button, with no handler. Nothing here calls the server.
//
// v1's Studio (Azimlearning/Arcana) was the reference for what a learner expects to find here (slides, quiz, and so on);
// nothing is ported from it.

/** The generators the Studio will offer, in the order they are shown. Names only: none has behaviour. */
const GENERATORS = ["Slides", "Quiz", "Flashcards", "Study session"] as const;

export function Studio() {
  return (
    <section aria-label="Studio generators" className="space-y-2">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">Studio</h2>
      <ul className="grid grid-cols-2 gap-2 text-sm">
        {GENERATORS.map((name) => (
          <li
            key={name}
            data-available="false"
            className="rounded-lg border border-dashed border-stone-300 bg-stone-100 p-2 text-stone-500"
          >
            <div className="font-medium text-stone-600">{name}</div>
            <div className="text-xs">Coming with the Studio agent</div>
          </li>
        ))}
      </ul>
    </section>
  );
}
