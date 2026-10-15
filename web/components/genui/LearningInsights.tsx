"use client";

// The learner's own position (D-43, V5): coverage and bands of mastery, the weakest pages, the last 14 days of activity and the review
// workload for the next 7. New in v2; the Studio's counterpart of VERA AI's "Analytics" function, aimed at the learner and with nothing
// fitted that the data cannot support.
//
// Structural precondition (constraint 7): the learner has rated at least one page the vault holds. The server validator derives every
// figure again from the vault, the mastery, the dates of the ratings and the activity, and requires exactly this block, so the client
// computes nothing: it only draws. A trend is drawn only when the server sent one (it sends one only with 7 active days of 14), and the
// bars have the numbers beside them, so nothing is carried by length or colour alone.

import type { LearningInsights as LearningInsightsBlock } from "@arcana/schema";

import { EmptyState, ErrorState, Frame, LoadingState, PartialState } from "./BlockStates";
import { PageName } from "./notesNav";

export function LearningInsights({ block }: { block: LearningInsightsBlock }) {
  const { meta } = block;
  switch (meta.status) {
    case "loading":
      return <LoadingState caption="Working out your insights…" rows={4} />;
    case "empty":
      return (
        <EmptyState
          title="No insights yet."
          hint="Rate a page (I know this, unsure, I don't know this yet) and your position will appear here."
        />
      );
    case "error":
      return <ErrorState error={meta.error} fallback="Your insights could not be shown." />;
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

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const shortDate = (iso: string) => iso.slice(5);

/** A bar whose length is the value over the largest value shown; the number is always written beside it. */
function Bar({ value, max }: { value: number; max: number }) {
  const width = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <span aria-hidden="true" className="inline-block h-2 rounded bg-emerald-500" style={{ width: `${Math.max(width, value > 0 ? 4 : 0)}%` }} />
  );
}

function Body({ block }: { block: LearningInsightsBlock }) {
  const { asOf, pages, ratedPages, bands, weakest, activity, activeDays, trend, workload } = block.data;
  const peakActivity = Math.max(1, ...activity.map((d) => d.count));
  const peakDue = Math.max(1, ...workload.map((d) => d.due));
  const coverage = pages > 0 ? Math.round((ratedPages / pages) * 100) : 0;
  const total = activity.reduce((n, d) => n + d.count, 0);

  return (
    <div className="space-y-5">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-600">Learning insights</h2>
        <p className="text-xs text-stone-500">as of {asOf}</p>
      </div>

      <section aria-label="Mastery" className="space-y-2">
        <p className="text-sm text-stone-800">
          You have rated {plural(ratedPages, "page", "pages")} of the {pages} in your notes ({coverage} percent).
        </p>
        <dl className="grid grid-cols-3 gap-2 text-center text-sm">
          <div className="rounded-md bg-red-50 p-2">
            <dt className="text-xs text-red-800">Needs work</dt>
            <dd className="text-lg font-semibold text-red-900">{bands.needsWork}</dd>
          </div>
          <div className="rounded-md bg-amber-50 p-2">
            <dt className="text-xs text-amber-800">Getting there</dt>
            <dd className="text-lg font-semibold text-amber-900">{bands.gettingThere}</dd>
          </div>
          <div className="rounded-md bg-emerald-50 p-2">
            <dt className="text-xs text-emerald-800">Comfortable</dt>
            <dd className="text-lg font-semibold text-emerald-900">{bands.comfortable}</dd>
          </div>
        </dl>
        {weakest.length > 0 && (
          <div>
            <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-stone-500">Weakest first</h3>
            <ol className="space-y-1 text-sm">
              {weakest.map((w) => (
                <li key={w.pageId} className="flex flex-wrap items-baseline gap-2">
                  <span className="font-medium text-stone-900">
                    <PageName id={w.pageId} label={w.pageLabel} />
                  </span>
                  <span className="text-xs text-stone-500">
                    {Math.round(w.score * 100)} percent from {plural(w.events, "rating", "ratings")}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </section>

      <section aria-label="Activity">
        <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-stone-500">Ratings in the last {activity.length} days</h3>
        <table className="w-full text-xs">
          <caption className="sr-only">Ratings recorded on each of the last {activity.length} days</caption>
          <thead className="sr-only">
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Ratings</th>
            </tr>
          </thead>
          <tbody>
            {activity.map((d) => (
              <tr key={d.date}>
                <th scope="row" className="w-14 py-0.5 text-left font-normal text-stone-500">
                  {shortDate(d.date)}
                </th>
                <td className="py-0.5">
                  <span className="flex items-center gap-2">
                    <span className="inline-block w-full max-w-xs">
                      <Bar value={d.count} max={peakActivity} />
                    </span>
                    <span className="w-6 text-right text-stone-700">{d.count}</span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-xs text-stone-600">
          {plural(total, "rating", "ratings")} on {plural(activeDays, "day", "days")}.{" "}
          {trend === null
            ? `No trend is drawn: a line needs at least 7 active days and there ${activeDays === 1 ? "is" : "are"} ${activeDays}.`
            : `Trend: ${trend.slopePerDay >= 0 ? "+" : ""}${trend.slopePerDay} ratings per day (a straight line through the ${activity.length} days; a 3-day average ends at ${trend.movingAverage[trend.movingAverage.length - 1]}).`}
        </p>
      </section>

      <section aria-label="Review workload">
        <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-stone-500">Pages due for review, next {workload.length} days</h3>
        <table className="w-full text-xs">
          <caption className="sr-only">Pages the review schedule would have due on each coming day</caption>
          <thead className="sr-only">
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Pages due</th>
            </tr>
          </thead>
          <tbody>
            {workload.map((d) => (
              <tr key={d.date}>
                <th scope="row" className="w-14 py-0.5 text-left font-normal text-stone-500">
                  {shortDate(d.date)}
                </th>
                <td className="py-0.5">
                  <span className="flex items-center gap-2">
                    <span className="inline-block w-full max-w-xs">
                      <Bar value={d.due} max={peakDue} />
                    </span>
                    <span className="w-6 text-right text-stone-700">{d.due}</span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <p className="text-xs text-stone-500">
        These are counts and a fixed rule over your own ratings, not a prediction. The workload applies the review schedule&apos;s rule forward
        and does not model further forgetting. A weekly pattern is not fitted: two weeks of ratings cannot separate one from noise.
      </p>
    </div>
  );
}
