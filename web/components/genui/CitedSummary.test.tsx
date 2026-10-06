import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TITLE, block, envelope } from "@/test/fixtures";

import { CitedSummary } from "./CitedSummary";

describe("CitedSummary: the five wire states", () => {
  it("loading: a busy status with a skeleton, and none of the answer", () => {
    render(<CitedSummary block={block("loading")} />);
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText(/Dense retrieval embeds/)).not.toBeInTheDocument();
  });

  it("empty: says nothing was found, and is not styled or announced as a failure", () => {
    render(<CitedSummary block={block("empty")} />);
    expect(screen.getByText("No evidence found in your documents.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert, with field paths and a retry hint", () => {
    const reason = envelope({
      code: "validation_failed",
      message: "The block failed content validation.",
      issues: [{ path: "data.citations.0.chunkId", message: "no stored chunk has this id" }],
      retryable: true,
    });
    render(<CitedSummary block={block("error", {}, reason)} />);
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("The block failed content validation.")).toBeInTheDocument();
    expect(within(alert).getByText("data.citations.0.chunkId")).toBeInTheDocument();
    expect(within(alert).getByText(/try again/i)).toBeInTheDocument();
  });

  it("error: does not offer a retry when the error is not retryable", () => {
    render(<CitedSummary block={block("error", {}, envelope({ retryable: false }))} />);
    expect(screen.queryByText(/try again/i)).not.toBeInTheDocument();
  });

  it("error without a reason still renders a message, never a blank panel", () => {
    render(<CitedSummary block={block("error")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("could not be produced");
  });

  it("partial: shows what has arrived and says it is not final", () => {
    render(<CitedSummary block={block("partial")} />);
    expect(screen.getByText(/Dense retrieval embeds passages/)).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });

  it("ready: every segment is shown, in order, with its citation pills", () => {
    render(<CitedSummary block={block("ready")} />);
    const first = screen.getByText(/Dense retrieval embeds passages/);
    const second = screen.getByText(/BM25 scores exact terms/);
    expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/not final/i)).not.toBeInTheDocument();
  });
});

describe("CitedSummary: citations name their source document", () => {
  it("a pill carries the document title and page, and links to its source entry", () => {
    render(<CitedSummary block={block("ready")} />);
    // c1 supports both segments in the fixture, so it appears as two pills, both labelled the same
    const pills = screen.getAllByRole("link", { name: `Source c1: ${TITLE}, page 1` });
    expect(pills).toHaveLength(2);
    for (const pill of pills) {
      expect(pill).toHaveAttribute("href", "#turn-1-c1");
      expect(pill).toHaveAttribute("title", "Dense Retrieval embeds passages and queries.");
    }
    expect(document.getElementById("turn-1-c1")).toBeInTheDocument(); // the link target exists
  });

  it("the Sources list shows title, page and the quote for each citation", () => {
    render(<CitedSummary block={block("ready")} />);
    const sources = screen.getByRole("region", { name: "Sources" });
    expect(within(sources).getAllByText(TITLE)).toHaveLength(2);
    expect(within(sources).getByText(/page 1/)).toBeInTheDocument();
    expect(within(sources).getByText("Dense Retrieval embeds passages and queries.")).toBeInTheDocument();
  });

  it("a citation with no page number omits the page rather than printing null", () => {
    render(<CitedSummary block={block("ready")} />);
    const pill = screen.getByRole("link", { name: `Source c2: ${TITLE}` });
    expect(pill).toBeInTheDocument();
    expect(screen.queryByText(/page null|page undefined/)).not.toBeInTheDocument();
  });

  it("a segment may cite several sources", () => {
    render(<CitedSummary block={block("ready")} />);
    expect(screen.getAllByRole("link", { name: /^Source c1/ })).toHaveLength(2); // cited by both segments
    expect(screen.getAllByRole("link", { name: /^Source c2/ })).toHaveLength(1);
  });

  it("never renders a dead pill for a citation id that is not in the block", () => {
    const b = block("ready", { segments: [{ text: "Claim.", citationIds: ["c1", "ghost"] }] });
    render(<CitedSummary block={b} />);
    expect(screen.queryByRole("link", { name: /ghost/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Source c1/ })).toBeInTheDocument();
  });

  it("keeps a source's id on one line, however narrow the column and however long the title", () => {
    render(<CitedSummary block={block("ready")} />);
    const ids = screen.getAllByText(/^\[c\d\]$/);
    expect(ids.length).toBeGreaterThan(0);
    for (const id of ids) expect(id).toHaveClass("shrink-0"); // a squeezed flex child would otherwise break between letters
  });
});

describe("CitedSummary: anchors", () => {
  it("builds every fragment from ids with only letters, digits, underscores and hyphens", () => {
    const odd = block("ready");
    odd.id = "turn 1/x";
    odd.data.segments = [{ text: "Dense retrieval embeds passages.", citationIds: ["c 1"] }];
    odd.data.citations = [{ ...odd.data.citations[0]!, id: "c 1" }];
    const { container } = render(<CitedSummary block={odd} />);
    const href = container.querySelector("a[href^='#']")!.getAttribute("href")!;
    expect(href).toBe("#turn_1_x-c_1");
    expect(container.querySelector("[id='turn_1_x-c_1']")).not.toBeNull();
  });
});
