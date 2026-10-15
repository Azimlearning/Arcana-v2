import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { envelope, studySet } from "@/test/fixtures";

import { StudySet } from "./StudySet";

afterEach(() => vi.restoreAllMocks());

describe("StudySet: the five wire states", () => {
  it("loading: a busy status and no items", () => {
    render(<StudySet block={studySet("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("region", { name: "Study items" })).not.toBeInTheDocument();
  });

  it("empty: says nothing could be made, with the count passed over, and is not a failure", () => {
    render(<StudySet block={studySet("empty", { skipped: 2 })} />);
    expect(screen.getByText("No study items could be made.")).toBeInTheDocument();
    expect(screen.getByText(/2 pages were looked at/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason as an alert", () => {
    render(<StudySet block={studySet("error", {}, envelope({ message: "The set failed validation." }))} />);
    expect(within(screen.getByRole("alert")).getByText("The set failed validation.")).toBeInTheDocument();
  });

  it("partial: says it is not final", () => {
    render(<StudySet block={studySet("partial")} />);
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });

  it("ready: the prompts show and none of the sentences do until asked", () => {
    render(<StudySet block={studySet("ready")} />);
    const items = screen.getByRole("region", { name: "Study items" });
    expect(within(items).getByText("dense retrieval")).toBeInTheDocument();
    expect(screen.queryByText(/embedding vectors of the query/)).not.toBeInTheDocument(); // withheld until revealed
    expect(screen.getByText(/prompts for your own recall/)).toBeInTheDocument();
  });
});

describe("StudySet: revealing and rating", () => {
  it("revealing shows the cited sentence and its source, as text", () => {
    render(<StudySet block={studySet("ready")} />);
    fireEvent.click(screen.getByRole("button", { name: "Show the definition" }));
    expect(screen.getByText(/embedding vectors of the query/)).toBeInTheDocument();
    expect(screen.getByText(/Paper One · page 3/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Rate yourself" })).toBeInTheDocument();
  });

  it("a hint is behind a button and is shown only when asked for", () => {
    render(<StudySet block={studySet("ready", { kind: "socratic" }, null, { hint: "Look at Paper Two, page 5." })} />);
    expect(screen.queryByText("Look at Paper Two, page 5.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show a hint" }));
    expect(screen.getByText("Look at Paper Two, page 5.")).toBeInTheDocument();
  });

  it("a rating is recorded for the item's page and reported", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    render(<StudySet block={studySet("ready")} />);
    fireEvent.click(screen.getByRole("button", { name: "Show the definition" }));
    fireEvent.click(screen.getByRole("button", { name: "I was unsure" }));
    await waitFor(() => expect(screen.getByText("Saved.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ pageId: "dense_retrieval", signal: "unsure" });
    vi.unstubAllGlobals();
  });

  it("a failed save says so and does not claim it was saved", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<StudySet block={studySet("ready")} />);
    fireEvent.click(screen.getByRole("button", { name: "Show the definition" }));
    fireEvent.click(screen.getByRole("button", { name: "I knew this" }));
    await waitFor(() => expect(screen.getByText("Could not save your rating.")).toBeInTheDocument());
    expect(screen.queryByText("Saved.")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("a Cornell set shows its summary", () => {
    render(<StudySet block={studySet("ready", { kind: "cornell" }, null, {}, true)} />);
    expect(screen.getByRole("region", { name: "Summary" })).toBeInTheDocument();
  });
});
