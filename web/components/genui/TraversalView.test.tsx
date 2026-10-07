import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TITLE, envelope, traversalView } from "@/test/fixtures";

import { TraversalView } from "./TraversalView";

const node = (name: string) => screen.getByRole("button", { name: new RegExp(`^${name},`) });

describe("TraversalView: the wire states", () => {
  it("loading: a busy status and no diagram", () => {
    render(<TraversalView block={traversalView("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("empty: says there is no path to show, not styled or announced as a failure", () => {
    render(<TraversalView block={traversalView("empty")} />);
    expect(screen.getByText("No search path to show.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert", () => {
    render(<TraversalView block={traversalView("error", {}, envelope({ message: "The graph store is unreadable." }))} />);
    expect(within(screen.getByRole("alert")).getByText("The graph store is unreadable.")).toBeInTheDocument();
  });

  it("partial: shows what is there and says it is not final", () => {
    render(<TraversalView block={traversalView("partial")} />);
    expect(screen.getByRole("group", { name: /Search path of 3 concepts/ })).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });
});

describe("TraversalView: ready", () => {
  it("says what it shows (the route, not what the documents state) and names the diagram", () => {
    render(<TraversalView block={traversalView("ready")} />);
    expect(screen.getByText(/the route the search took, not what your documents state/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Search path of 3 concepts and 2 steps" })).toBeInTheDocument();
  });

  it("lists every step as text with the stored relation read with spaces, and a link to the passage it came from", () => {
    render(<TraversalView block={traversalView("ready")} />);
    const steps = within(screen.getByRole("region", { name: "Steps" })).getAllByRole("listitem");
    expect(steps).toHaveLength(2);
    expect(steps[0]).toHaveTextContent("Dense Retrieval contrasted with BM25");
    expect(within(steps[1]!).getByRole("link", { name: /Passage c2/ })).toHaveAttribute("href", "#turn-1-traversal-view-c2");
  });

  it("lists the passages reached in rank order, each saying how it was reached in words, with its quote", () => {
    render(<TraversalView block={traversalView("ready")} />);
    const passages = within(screen.getByRole("region", { name: "Passages reached" })).getAllByRole("listitem");
    expect(passages).toHaveLength(3);
    expect(passages[0]).toHaveTextContent("mentions Dense Retrieval, BM25");
    expect(passages[1]).toHaveTextContent("an edge from Dense Retrieval was found in it");
    expect(passages[2]).toHaveTextContent("mentions a concept next to BM25");
    expect(passages[0]).toHaveTextContent(TITLE);
    expect(passages[0]).toHaveTextContent("Dense Retrieval alone and BM25 alone are two arms.");
    expect(passages[0]!.id).toBe("turn-1-traversal-view-c1");
  });

  it("every concept is a focusable button saying whether it came from the question and how it matched", () => {
    render(<TraversalView block={traversalView("ready")} />);
    const nodes = screen.getAllByRole("button").filter((b) => b.getAttribute("tabindex") === "0" && b.closest("svg"));
    expect(nodes.map((n) => n.getAttribute("aria-label"))).toEqual([
      "Dense Retrieval, a concept from your question (exact match), 2 steps",
      "BM25, a concept from your question (partial match), 1 step",
      "Reciprocal Rank Fusion, reached by a relation, 1 step",
    ]);
  });

  it("says how many followed relations it left out", () => {
    const first = render(<TraversalView block={traversalView("ready")} />);
    expect(screen.getByText(/7 other relations followed from these concepts led to passages the search did not return/)).toBeInTheDocument();
    first.unmount();
    const second = render(<TraversalView block={traversalView("ready", { stepsLeftOut: 1 })} />);
    expect(screen.getByText(/1 other relation followed .* and is not shown/)).toBeInTheDocument();
    second.unmount();
    render(<TraversalView block={traversalView("ready", { stepsLeftOut: 0 })} />);
    expect(screen.queryByText(/not shown/)).not.toBeInTheDocument();
  });

  it("starts with nothing selected and tells the user what to do", () => {
    render(<TraversalView block={traversalView("ready")} />);
    expect(within(screen.getByRole("region", { name: "Details" })).getByText(/Select a concept or a passage/)).toBeInTheDocument();
    for (const n of screen.getAllByRole("button").filter((b) => b.closest("svg"))) expect(n).toHaveAttribute("aria-pressed", "false");
  });
});

describe("TraversalView: selection", () => {
  it("clicking a concept shows the steps and passages that connect to it and marks it pressed", () => {
    render(<TraversalView block={traversalView("ready")} />);
    fireEvent.click(node("BM25"));
    expect(node("BM25")).toHaveAttribute("aria-pressed", "true");
    const details = screen.getByRole("region", { name: "Details" });
    expect(details).toHaveTextContent("BM25");
    expect(details).toHaveTextContent("1 step and 2 passages connect to this concept");
    expect(details).toHaveTextContent("Dense Retrieval contrasted with BM25");
  });

  it("Enter and Space select a concept, and a second press clears it", () => {
    render(<TraversalView block={traversalView("ready")} />);
    fireEvent.keyDown(node("Dense Retrieval"), { key: "Enter" });
    expect(node("Dense Retrieval")).toHaveAttribute("aria-pressed", "true");
    fireEvent.keyDown(node("Dense Retrieval"), { key: " " });
    expect(node("Dense Retrieval")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("region", { name: "Details" })).toHaveTextContent(/Select a concept or a passage/);
  });

  it("clicking a passage shows the steps found in it and the concepts that reach it", () => {
    render(<TraversalView block={traversalView("ready")} />);
    fireEvent.click(within(screen.getByRole("region", { name: "Passages reached" })).getAllByRole("button")[1]!);
    const details = screen.getByRole("region", { name: "Details" });
    expect(details).toHaveTextContent("Passage 2");
    expect(details).toHaveTextContent("Dense Retrieval merged by Reciprocal Rank Fusion");
    expect(node("Dense Retrieval")).not.toHaveAttribute("aria-pressed", "true"); // the passage is selected, not a concept
  });

  it("a selection whose target is gone after the block is replaced is no selection", () => {
    const { rerender } = render(<TraversalView block={traversalView("ready")} />);
    fireEvent.click(node("Reciprocal Rank Fusion"));
    rerender(
      <TraversalView
        block={traversalView("ready", {
          seeds: [{ nodeId: "dense", match: "exact" }],
          nodes: [{ id: "dense", label: "Dense Retrieval" }],
          steps: [],
          reached: [{ citationId: "c1", via: "mentions", rank: 1, seedIds: ["dense"] }],
          citations: [{ id: "c1", chunkId: "d_c_1", docId: "d", docTitle: TITLE, page: 3, quote: "Dense Retrieval alone and BM25 alone are two arms." }],
          stepsLeftOut: 0,
        })}
      />,
    );
    expect(screen.getByRole("region", { name: "Details" })).toHaveTextContent(/Select a concept or a passage/);
  });
});

describe("TraversalView: text only", () => {
  it("renders hostile labels, relations and quotes as text, never as markup", () => {
    const hostile = "<img src=x onerror=alert(1)>";
    const block = traversalView("ready");
    block.data.nodes[0]!.label = hostile;
    block.data.steps[0]!.relation = "<b>bold</b>";
    block.data.citations[0]!.quote = "<script>alert(1)</script>";
    const { container } = render(<TraversalView block={block} />);
    expect(container.querySelector("img, b, script")).toBeNull();
    expect(container.textContent).toContain(hostile);
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });

  it("builds every fragment from ids with only letters, digits, underscores and hyphens", () => {
    const block = traversalView("ready");
    block.id = "turn 1/x";
    block.data.citations[0]!.id = "c 1";
    block.data.reached[0]!.citationId = "c 1";
    block.data.steps[0]!.citationId = "c 1";
    const { container } = render(<TraversalView block={block} />);
    expect(container.querySelector("a[href='#turn_1_x-c_1']")).not.toBeNull();
    expect(container.querySelector("[id='turn_1_x-c_1']")).not.toBeNull();
  });
});
