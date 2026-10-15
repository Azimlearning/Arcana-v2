import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { envelope, studyPlan } from "@/test/fixtures";

import { StudyPlan } from "./StudyPlan";

describe("StudyPlan: the five wire states", () => {
  it("loading: a busy status", () => {
    render(<StudyPlan block={studyPlan("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  });

  it("empty: says nothing is rated yet and tells the learner how to start, not as a failure", () => {
    render(<StudyPlan block={studyPlan("empty")} />);
    expect(screen.getByText("Nothing to review yet.")).toBeInTheDocument();
    expect(screen.getByText(/Rate a page/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason as an alert", () => {
    render(<StudyPlan block={studyPlan("error", {}, envelope({ message: "The schedule failed validation." }))} />);
    expect(within(screen.getByRole("alert")).getByText("The schedule failed validation.")).toBeInTheDocument();
  });

  it("partial: says it is not final", () => {
    render(<StudyPlan block={studyPlan("partial")} />);
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });

  it("ready: pages in the order sent, each with when it is due in words, the day count and its mastery in words", () => {
    render(<StudyPlan block={studyPlan("ready")} />);
    const list = screen.getByRole("region", { name: "Review schedule" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]!).getByText("Review now")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("BM25")).toBeInTheDocument();
    expect(within(rows[0]!).getByText(/needs work · rated 3 times · 1 day ago/)).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Review soon")).toBeInTheDocument();
    expect(within(rows[2]!).getByText(/comfortable · rated 6 times · today/)).toBeInTheDocument();
  });

  it("says how many rated pages it left out, and that the rule is a fixed interval and not a model", () => {
    render(<StudyPlan block={studyPlan("ready")} />);
    expect(screen.getByText(/2 more of 5 rated pages are not shown/)).toBeInTheDocument();
    expect(screen.getByText(/fixed interval, not a model/)).toBeInTheDocument();
    expect(screen.getByText("as of 2026-10-15")).toBeInTheDocument();
  });
});
