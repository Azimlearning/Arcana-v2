import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TITLE, envelope, graphView } from "@/test/fixtures";

import { GraphView } from "./GraphView";

const node = (name: string) => screen.getByRole("button", { name: new RegExp(`^${name},`) });

describe("GraphView: the wire states", () => {
  it("loading: a busy status and no graph", () => {
    render(<GraphView block={graphView("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("empty: says nothing was found, not styled or announced as a failure", () => {
    render(<GraphView block={graphView("empty")} />);
    expect(screen.getByText("No connections found.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert", () => {
    render(<GraphView block={graphView("error", {}, envelope({ message: "The graph store is unreadable." }))} />);
    expect(within(screen.getByRole("alert")).getByText("The graph store is unreadable.")).toBeInTheDocument();
  });

  it("partial: draws what is there and says it is not final", () => {
    render(<GraphView block={graphView("partial")} />);
    expect(screen.getByRole("group", { name: /Graph of 3 concepts/ })).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });
});

describe("GraphView: ready", () => {
  it("names the diagram and lists every relation as text, each with a source link", () => {
    render(<GraphView block={graphView("ready")} />);
    expect(screen.getByRole("group", { name: "Graph of 3 concepts and 2 relations" })).toBeInTheDocument();
    const relations = within(screen.getByRole("region", { name: "Relations" })).getAllByRole("listitem");
    expect(relations).toHaveLength(2);
    expect(relations[0]).toHaveTextContent("Dense Retrieval contrasted with BM25");
    expect(within(relations[1]!).getByRole("link", { name: /Source c2 for Dense Retrieval merged by/ })).toHaveAttribute(
      "href",
      "#turn-1-graph-view-c2",
    );
    expect(screen.getByRole("region", { name: "Sources" })).toHaveTextContent(TITLE);
  });

  it("every concept is a focusable button, in the order given", () => {
    render(<GraphView block={graphView("ready")} />);
    const nodes = screen.getAllByRole("button").filter((b) => b.getAttribute("tabindex") === "0" && b.closest("svg"));
    expect(nodes.map((n) => n.getAttribute("aria-label"))).toEqual([
      "Dense Retrieval, 2 relations",
      "BM25, 1 relation",
      "Reciprocal Rank Fusion, 1 relation",
    ]);
  });

  it("starts with nothing selected and tells the user what to do", () => {
    render(<GraphView block={graphView("ready")} />);
    expect(node("Dense Retrieval")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("region", { name: "Details" })).toHaveTextContent("Select a concept or a relation");
  });

  it("selecting a concept by click shows each incident relation with its quote and source link", () => {
    render(<GraphView block={graphView("ready")} />);
    fireEvent.click(node("Dense Retrieval"));
    expect(node("Dense Retrieval")).toHaveAttribute("aria-pressed", "true"); // exposed to assistive technology
    const details = screen.getByRole("region", { name: "Details" });
    expect(within(details).getByRole("heading", { name: "Dense Retrieval" })).toBeInTheDocument();
    expect(details).toHaveTextContent("Dense Retrieval alone and BM25 alone are two arms.");
    expect(details).toHaveTextContent("Reciprocal Rank Fusion merges Dense Retrieval with the others.");
    expect(within(details).getByRole("link", { name: `${TITLE}, page 3` })).toHaveAttribute("href", "#turn-1-graph-view-c1");
  });

  it("selecting a leaf concept shows only its own relation", () => {
    render(<GraphView block={graphView("ready")} />);
    fireEvent.click(node("BM25"));
    const details = screen.getByRole("region", { name: "Details" });
    expect(details).toHaveTextContent("Dense Retrieval alone and BM25 alone are two arms.");
    expect(details).not.toHaveTextContent("Reciprocal Rank Fusion merges");
  });

  it("works from the keyboard: Enter and Space select, a second press clears", () => {
    render(<GraphView block={graphView("ready")} />);
    fireEvent.keyDown(node("BM25"), { key: "Enter" });
    expect(node("BM25")).toHaveAttribute("aria-pressed", "true");
    fireEvent.keyDown(node("BM25"), { key: "Enter" });
    expect(node("BM25")).toHaveAttribute("aria-pressed", "false");
    fireEvent.keyDown(node("Reciprocal Rank Fusion"), { key: " " });
    expect(node("Reciprocal Rank Fusion")).toHaveAttribute("aria-pressed", "true");
    fireEvent.keyDown(node("Reciprocal Rank Fusion"), { key: "a" }); // any other key does nothing
    expect(node("Reciprocal Rank Fusion")).toHaveAttribute("aria-pressed", "true");
  });

  it("selecting a relation from the list shows its quote and marks it pressed", () => {
    render(<GraphView block={graphView("ready")} />);
    const row = screen.getByRole("button", { name: /Dense Retrieval merged by Reciprocal Rank Fusion/ });
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-pressed", "true");
    const details = screen.getByRole("region", { name: "Details" });
    expect(within(details).getByRole("heading", { name: "Selected relation" })).toBeInTheDocument();
    expect(details).toHaveTextContent("Reciprocal Rank Fusion merges Dense Retrieval");
    expect(details).not.toHaveTextContent("Dense Retrieval alone and BM25");
  });

  it("keeps the selection when the same block is rendered again, and drops it if its target is gone", () => {
    const { rerender } = render(<GraphView block={graphView("ready")} />);
    fireEvent.click(node("BM25"));
    rerender(<GraphView block={graphView("ready")} />);
    expect(node("BM25")).toHaveAttribute("aria-pressed", "true");

    rerender(<GraphView block={graphView("ready", { nodes: [{ id: "dense", label: "Dense Retrieval" }, { id: "rrf", label: "Reciprocal Rank Fusion" }], edges: [{ source: "dense", target: "rrf", relation: "merged by", citationId: "c2" }] })} />);
    expect(screen.getByRole("region", { name: "Details" })).toHaveTextContent("Select a concept or a relation");
  });

  it("renders labels, relations and quotes as text, never as markup", () => {
    const hostile = "<img src=x onerror=alert(1)>";
    const block = graphView("ready", {
      nodes: [{ id: "a", label: hostile }, { id: "b", label: "B" }],
      edges: [{ source: "a", target: "b", relation: "<b>bold</b>", citationId: "c1" }],
      citations: [{ id: "c1", chunkId: "k", docId: "d", docTitle: "<script>x</script>", page: 1, quote: `${hostile} and B` }],
    });
    const { container } = render(<GraphView block={block} />);
    fireEvent.click(screen.getByRole("button", { name: /^<img.*, 1 relation$/ }));
    expect(container.querySelector("img, script, b")).toBeNull();
    expect(screen.getAllByText(/<img src=x onerror=alert\(1\)>/).length).toBeGreaterThan(0);
  });
});
