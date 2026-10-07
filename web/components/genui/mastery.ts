// How the screen words and colours a mastery score (D-35 A6). The wire carries the score (a belief in [0, 1] that decays towards
// ignorance), never these words. Colour is never the only cue: every place that colours a page by mastery also says it in words.

/** From this score a concept reads as comfortable, and from the next one as getting there. */
export const COMFORTABLE = 0.67;
export const GETTING_THERE = 0.4;

export type MasteryBand = "none" | "comfortable" | "getting-there" | "needs-work";

export function band(score: number | null): MasteryBand {
  if (score === null) return "none";
  if (score >= COMFORTABLE) return "comfortable";
  if (score >= GETTING_THERE) return "getting-there";
  return "needs-work";
}

export const BAND_WORDS: Record<MasteryBand, string> = {
  none: "not rated yet",
  comfortable: "comfortable",
  "getting-there": "getting there",
  "needs-work": "needs work",
};

/** The fill of a page's circle: pale stone for a page not rated yet, then three clearly different hues. */
export const BAND_FILL: Record<MasteryBand, string> = {
  none: "fill-stone-100",
  comfortable: "fill-emerald-300",
  "getting-there": "fill-amber-200",
  "needs-work": "fill-rose-300",
};

export const BAND_SWATCH: Record<MasteryBand, string> = {
  none: "bg-stone-100",
  comfortable: "bg-emerald-300",
  "getting-there": "bg-amber-200",
  "needs-work": "bg-rose-300",
};
