// The learner's review schedule (P5 S3, D-42): which rated pages to revisit and how soon. New in v2.
//
// Structural precondition (constraint 7): the learner has rated at least one page the vault holds. The server validator derives the
// schedule again from the vault, the mastery and the dates of the ratings and requires exactly this block, so the client never
// computes a due date. The rule is stated on screen: it is a fixed interval over the same mastery the notes colours show, not a
// trained scheduler. A page name opens the page when the screen can (the notes view), else it is plain text.

import type { PlanDue, StudyPlan as StudyPlanBlock } from "@arcana/schema";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { BAND_WORDS, band } from "./mastery";
import { PageName } from "./notesNav";

const DUE_WORDS: Record<PlanDue, string> = { now: "Review now", soon: "Review soon", later: "Later" };
const DUE_STYLE: Record<PlanDue, string> = {
  now: "bg-red-100 text-red-800",
  soon: "bg-amber-100 text-amber-800",
  later: "bg-stone-100 text-stone-700",
};

export function StudyPlan({ block }: { block: StudyPlanBlock }) {
  const { meta } = block;
  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Working out what to review…" rows={3} />;
    case "empty":
      return (
        <EmptyState
          title="Nothing to review yet."
          hint="Rate a page (I know this, unsure, I don't know this yet) and it will appear here with when to revisit it."
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="The review schedule could not be shown." />;
    case "partial":
      return (
        <PartialState>
          <Body block={block} />
        </PartialState>
      );
    case "ready":
      return (
        <Frame>
          <Body block={block} />
        </Frame>
      );
  }
}

function Body({ block }: { block: StudyPlanBlock }) {
  const { asOf, items, ratedPages, leftOut } = block.data;
  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-600">Review schedule</h2>
        <p className="text-xs text-stone-500">as of {asOf}</p>
      </div>
      <section aria-label="Review schedule">
        <ol className="space-y-2">
          {items.map((item) => {
            const mastery = band(item.score);
            return (
              <li key={item.pageId} className="flex flex-wrap items-center gap-2 rounded-md border border-stone-200 px-3 py-2">
                <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${DUE_STYLE[item.due]}`}>{DUE_WORDS[item.due]}</span>
                <span className="font-medium text-stone-900">
                  <PageName id={item.pageId} label={item.pageLabel} />
                </span>
                <span className="text-xs text-stone-500">
                  {BAND_WORDS[mastery]} · rated {item.events} {item.events === 1 ? "time" : "times"} ·{" "}
                  {item.daysSince === 0 ? "today" : `${item.daysSince} ${item.daysSince === 1 ? "day" : "days"} ago`}
                </span>
              </li>
            );
          })}
        </ol>
      </section>
      <p className="text-xs text-stone-500">
        {leftOut > 0 ? `${leftOut} more of ${ratedPages} rated pages are not shown. ` : ""}
        Pages you know less are due sooner; a page you know well comes back after about a week. This is a fixed interval, not a model.
      </p>
    </div>
  );
}
