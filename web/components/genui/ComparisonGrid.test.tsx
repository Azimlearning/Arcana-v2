import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TITLE, comparisonGrid, envelope } from "@/test/fixtures";

import { ComparisonGrid } from "./ComparisonGrid";

describe("ComparisonGrid: the wire states", () => {
  it("loading: a busy status and no table", () => {
    render(<ComparisonGrid block={comparisonGrid("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("empty: says there is nothing to compare, not styled or announced as a failure", () => {
    render(<ComparisonGrid block={comparisonGrid("empty")} />);
    expect(screen.getByText("Nothing to compare.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert", () => {
    render(<ComparisonGrid block={comparisonGrid("error", {}, envelope({ message: "No alignment was possible." }))} />);
    expect(within(screen.getByRole("alert")).getByText("No alignment was possible.")).toBeInTheDocument();
  });

  it("partial: shows the table and says it is not final", () => {
    render(<ComparisonGrid block={comparisonGrid("partial")} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });
});

describe("ComparisonGrid: ready", () => {
  it("is a table with a caption, column headers for entities and row headers for documents", () => {
    render(<ComparisonGrid block={comparisonGrid("ready")} />);
    const table = screen.getByRole("table", { name: "Comparison of 3 documents on 2 shared concepts" });
    expect(within(table).getByRole("columnheader", { name: "Dense Retrieval" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "BM25" })).toBeInTheDocument();
    for (const title of [TITLE, "Second Paper", "Third Paper"]) {
      expect(within(table).getByRole("rowheader", { name: title })).toBeInTheDocument();
    }
  });

  it("puts each quote in the right cell, with a source link to its entry in the Sources list", () => {
    render(<ComparisonGrid block={comparisonGrid("ready")} />);
    const row = screen.getByRole("rowheader", { name: TITLE }).closest("tr")!;
    const cells = within(row).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("Dense Retrieval embeds queries.");
    expect(cells[1]).toHaveTextContent("BM25 scores exact terms.");
    expect(within(cells[1]!).getByRole("link", { name: `Source c2: ${TITLE}, page 2` })).toHaveAttribute(
      "href",
      "#turn-1-comparison-grid-c2",
    );
    expect(document.getElementById("turn-1-comparison-grid-c2")).toHaveTextContent("BM25 scores exact terms.");
  });

  it("marks a missing cell in words, not as a blank or a guess", () => {
    render(<ComparisonGrid block={comparisonGrid("ready")} />);
    const row = screen.getByRole("rowheader", { name: "Second Paper" }).closest("tr")!;
    const cells = within(row).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("Dense Retrieval underpins");
    expect(cells[1]).toHaveTextContent("No evidence in this paper");
    expect(screen.getAllByText("No evidence in this paper")).toHaveLength(1); // only where evidence is absent
  });

  it("shortens a long quote and expands it on request, exposing the state", () => {
    render(<ComparisonGrid block={comparisonGrid("ready")} />);
    const row = screen.getByRole("rowheader", { name: "Second Paper" }).closest("tr")!;
    const more = within(row).getByRole("button", { name: /Show more: Second Paper, Dense Retrieval/ });
    expect(more).toHaveAttribute("aria-expanded", "false");
    expect(within(row).queryByText(/across many sentences/)).not.toBeInTheDocument();
    fireEvent.click(more);
    const less = within(row).getByRole("button", { name: /Show less: Second Paper, Dense Retrieval/ });
    expect(less).toHaveAttribute("aria-expanded", "true");
    expect(within(row).getByText(/across many sentences/)).toBeInTheDocument();
    fireEvent.click(less);
    expect(within(row).queryByText(/across many sentences/)).not.toBeInTheDocument();
  });

  it("the table scrolls as a labelled, focusable region, and says so plainly if a cell's citation is missing", () => {
    const grid = comparisonGrid("ready");
    grid.data.citations = grid.data.citations.filter((c) => c.id !== "c2");
    render(<ComparisonGrid block={grid} />);
    expect(screen.getByRole("region", { name: "Comparison table" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("alert")).toHaveTextContent("Evidence for this cell is unavailable.");
    expect(screen.getAllByText("No evidence in this paper")).toHaveLength(1); // a missing citation is not "no evidence"
  });

  it("a short quote has no expand control", () => {
    render(<ComparisonGrid block={comparisonGrid("ready")} />);
    const row = screen.getByRole("rowheader", { name: TITLE }).closest("tr")!;
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders titles, labels and quotes as text, never as markup", () => {
    const hostile = "<img src=x onerror=alert(1)>";
    const block = comparisonGrid("ready", {
      dimensions: [{ id: "a", label: hostile }, { id: "b", label: "B" }],
      rows: [
        { docId: "d1", docTitle: "<b>Bold</b>", cells: [{ dimensionId: "a", citationId: "c1" }, { dimensionId: "b", citationId: "c1" }] },
        { docId: "d2", docTitle: "Other", cells: [{ dimensionId: "a", citationId: "c2" }, { dimensionId: "b", citationId: "c2" }] },
      ],
      citations: [
        { id: "c1", chunkId: "k", docId: "d1", docTitle: "<b>Bold</b>", page: 1, quote: `${hostile} and B` },
        { id: "c2", chunkId: "k", docId: "d2", docTitle: "Other", page: 1, quote: `${hostile} and B too` },
      ],
    });
    const { container } = render(<ComparisonGrid block={block} />);
    expect(container.querySelector("img, b, script")).toBeNull();
    expect(screen.getByRole("columnheader", { name: hostile })).toBeInTheDocument();
  });
});
