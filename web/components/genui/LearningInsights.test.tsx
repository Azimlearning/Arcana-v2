import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { envelope, learningInsights } from "@/test/fixtures";

import { LearningInsights } from "./LearningInsights";
import { NotesNav } from "./notesNav";

describe("LearningInsights: the wire states", () => {
  it("loading: a busy status and none of the figures", () => {
    render(<LearningInsights block={learningInsights("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("region", { name: "Mastery" })).not.toBeInTheDocument();
  });

  it("empty: says how to get insights, and is not a failure", () => {
    render(<LearningInsights block={learningInsights("empty")} />);
    expect(screen.getByText("No insights yet.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert", () => {
    render(<LearningInsights block={learningInsights("error", {}, envelope({ message: "The learner file is locked." }))} />);
    expect(within(screen.getByRole("alert")).getByText("The learner file is locked.")).toBeInTheDocument();
  });

  it("partial: shows what is there and says it is not final", () => {
    render(<LearningInsights block={learningInsights("partial")} />);
    expect(screen.getByRole("region", { name: "Mastery" })).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });
});

describe("LearningInsights: ready", () => {
  it("says what is rated, gives the three bands in words and the weakest pages with their basis", () => {
    render(<LearningInsights block={learningInsights("ready")} />);
    const mastery = within(screen.getByRole("region", { name: "Mastery" }));
    expect(mastery.getByText(/You have rated 5 pages of the 20 in your notes \(25 percent\)/)).toBeInTheDocument();
    expect(mastery.getByText("Needs work").nextElementSibling).toHaveTextContent("2");
    expect(mastery.getByText("Comfortable").nextElementSibling).toHaveTextContent("2");
    expect(mastery.getByText("20 percent from 3 ratings")).toBeInTheDocument();
  });

  it("gives every day of the activity and of the workload as a table row with its number written", () => {
    render(<LearningInsights block={learningInsights("ready")} />);
    const activity = within(screen.getByRole("region", { name: "Activity" }));
    expect(activity.getAllByRole("row").length).toBeGreaterThanOrEqual(14);
    expect(activity.getByRole("row", { name: /10-15/ })).toHaveTextContent("3");
    const workload = within(screen.getByRole("region", { name: "Review workload" }));
    expect(workload.getByRole("row", { name: /10-22/ })).toHaveTextContent("5");
  });

  it("states the trend the server sent, in words", () => {
    render(<LearningInsights block={learningInsights("ready")} />);
    expect(screen.getByText(/Trend: \+0\.12 ratings per day/)).toBeInTheDocument();
  });

  it("with no trend says why none is drawn, and does not invent one", () => {
    render(<LearningInsights block={learningInsights("ready", { trend: null, activeDays: 3 })} />);
    expect(screen.getByText(/No trend is drawn: a line needs at least 7 active days and there are 3/)).toBeInTheDocument();
    expect(screen.queryByText(/Trend:/)).not.toBeInTheDocument();
  });

  it("says it is not a prediction and what it does not model", () => {
    render(<LearningInsights block={learningInsights("ready")} />);
    expect(screen.getByText(/not a prediction/)).toBeInTheDocument();
    expect(screen.getByText(/does not model further forgetting/)).toBeInTheDocument();
  });

  it("a page name opens the page when the notes screen can, and is plain text when it cannot", () => {
    const openPage = vi.fn();
    const { unmount } = render(
      <NotesNav.Provider value={{ openPage }}>
        <LearningInsights block={learningInsights("ready")} />
      </NotesNav.Provider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "BM25" }));
    expect(openPage).toHaveBeenCalledWith("bm25");
    unmount();
    render(<LearningInsights block={learningInsights("ready")} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
