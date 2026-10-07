import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { envelope, notesGraph } from "@/test/fixtures";

import { NotesGraph } from "./NotesGraph";
import { NotesNav } from "./notesNav";
import { ringLayout } from "./notesLayout";

describe("NotesGraph: the wire states", () => {
  it("loading: a busy status and no diagram", () => {
    render(<NotesGraph block={notesGraph("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("empty: says there are no pages yet", () => {
    render(<NotesGraph block={notesGraph("empty")} />);
    expect(screen.getByText("There are no pages yet.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("empty with a query: names what was searched, as a notice and not a failure", () => {
    render(<NotesGraph block={notesGraph("empty", { query: "zebra" })} />);
    expect(screen.getByText("No page matches “zebra”.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert", () => {
    render(<NotesGraph block={notesGraph("error", {}, envelope({ message: "The vault is unreadable." }))} />);
    expect(within(screen.getByRole("alert")).getByText("The vault is unreadable.")).toBeInTheDocument();
  });

  it("partial: shows what is there and says it is not final", () => {
    render(<NotesGraph block={notesGraph("partial")} />);
    expect(screen.getByRole("group", { name: /Page graph of 3 pages/ })).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });
});

describe("NotesGraph: ready", () => {
  it("names the diagram with the counts of stated and named-together links and explains the two kinds of line", () => {
    render(<NotesGraph block={notesGraph("ready")} />);
    expect(screen.getByRole("group", { name: "Page graph of 3 pages, 1 stated links and 1 named-together links" })).toBeInTheDocument();
    expect(screen.getByText(/A solid line is a relation the documents state; a dashed line only says two names occur in one sentence/)).toBeInTheDocument();
  });

  it("lists every page with its numbers as text, so nothing depends on the picture", () => {
    render(<NotesGraph block={notesGraph("ready")} />);
    const pages = within(screen.getByRole("region", { name: "Pages" })).getAllByRole("listitem");
    expect(pages).toHaveLength(3);
    expect(pages[0]).toHaveTextContent("Retrieval-Augmented Generation");
    expect(pages[0]).toHaveTextContent("2 passages · 2 documents · 2 links");
    expect(pages[2]).toHaveTextContent("1 passage · 1 document · 1 link");
  });

  it("says in words what a focused graph and a narrowed overview show", () => {
    const { rerender } = render(<NotesGraph block={notesGraph("ready", { focusId: "rag" })} />);
    expect(screen.getByText(/Retrieval-Augmented Generation and the pages linked to it/)).toBeInTheDocument();
    rerender(<NotesGraph block={notesGraph("ready", { query: "rag" })} />);
    expect(screen.getByText(/Pages that match “rag”, the most linked first/)).toBeInTheDocument();
  });

  it("says how many pages are not shown, and how to find them in an overview", () => {
    render(<NotesGraph block={notesGraph("ready", { nodesLeftOut: 12 })} />);
    expect(screen.getByText(/12 more pages are not shown/)).toBeInTheDocument();
    expect(screen.getByText(/Search for a concept to find it/)).toBeInTheDocument();
  });

  it("marks the page you are on in the accessible name", () => {
    render(<NotesGraph block={notesGraph("ready", { focusId: "rag" })} />);
    expect(screen.getByRole("button", { name: /^Retrieval-Augmented Generation, in 2 passages, linked to 2 pages, the page you are on/ })).toBeInTheDocument();
  });

  it("opens another page from the diagram or the list, and not the page you are already on", () => {
    const openPage = vi.fn();
    render(
      <NotesNav.Provider value={{ openPage }}>
        <NotesGraph block={notesGraph("ready", { focusId: "rag" })} />
      </NotesNav.Provider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Self-RAG, in 1 passage/ }));
    expect(openPage).toHaveBeenCalledWith("self_rag");
    const list = screen.getByRole("region", { name: "Pages" });
    fireEvent.click(within(list).getByRole("button", { name: "large language models" }));
    expect(openPage).toHaveBeenCalledWith("llm");
    fireEvent.click(within(list).getByRole("button", { name: "Retrieval-Augmented Generation" }));
    expect(openPage).toHaveBeenCalledTimes(2);
  });

  it("works from the keyboard: Enter on a page in the diagram opens it", () => {
    const openPage = vi.fn();
    render(
      <NotesNav.Provider value={{ openPage }}>
        <NotesGraph block={notesGraph("ready")} />
      </NotesNav.Provider>,
    );
    fireEvent.keyDown(screen.getByRole("button", { name: /^Self-RAG, in 1 passage/ }), { key: "Enter" });
    expect(openPage).toHaveBeenCalledWith("self_rag");
  });

  it("highlights a chosen page when the screen cannot open pages, and clears it when chosen again", () => {
    render(<NotesGraph block={notesGraph("ready")} />);
    const button = screen.getByRole("button", { name: /^Self-RAG, in 1 passage/ });
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-pressed", "false");
  });

  it("renders names as text, never as markup", () => {
    const hostile = notesGraph("ready");
    hostile.data.nodes[0]!.label = "<img src=x onerror=alert(1)>";
    const { container } = render(<NotesGraph block={hostile} />);
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("NotesGraph: which lines are drawn", () => {
  const lines = (container: HTMLElement) => container.querySelectorAll("svg g[aria-hidden] line");

  it("draws the lines the documents state, and a named-together line only for the page the graph is about or a chosen page", () => {
    const { container, rerender } = render(<NotesGraph block={notesGraph("ready")} />);
    expect(lines(container)).toHaveLength(1); // the overview: the one stated line; the co-mention is hidden
    rerender(<NotesGraph block={notesGraph("ready", { focusId: "rag" })} />);
    expect(lines(container)).toHaveLength(2); // both lines touch the focus
  });

  it("names an inner-circle page in the diagram only when it is chosen (the list below names every page)", () => {
    const many = notesGraph("ready", {
      nodes: Array.from({ length: 20 }, (_, i) => ({ id: `p${i}`, label: `Page ${i}`, kind: null, passages: 1, documents: 1, degree: 0 })),
      edges: [],
    });
    const { container } = render(<NotesGraph block={many} />);
    const labelled = () => container.querySelectorAll("svg text").length;
    expect(labelled()).toBe(10); // the outer circle only
    fireEvent.click(screen.getByRole("button", { name: /^Page 1, in 1 passage/ }));
    expect(labelled()).toBe(11);
  });

  it("draws exactly a chosen page's lines when one is chosen", () => {
    const { container } = render(<NotesGraph block={notesGraph("ready")} />);
    fireEvent.click(screen.getByRole("button", { name: /^large language models, in 1 passage/ }));
    expect(lines(container)).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: /^Self-RAG, in 1 passage/ }));
    expect(lines(container)).toHaveLength(1);
  });
});

describe("ringLayout", () => {
  it("puts every second page of a crowded ring on an inner circle", () => {
    const ids = Array.from({ length: 20 }, (_, i) => `p${i}`);
    const { pages } = ringLayout(null, ids);
    const radius = (p: { x: number; y: number }) => Math.hypot((p.x - 320) / 200, (p.y - 220) / 192);
    expect(radius(pages[0]!)).toBeCloseTo(1, 1);
    expect(radius(pages[1]!)).toBeCloseTo(0.82, 1);
    expect(pages.filter((p) => p.inner)).toHaveLength(10);
    expect(ringLayout(null, ids.slice(0, 10)).pages.every((p) => Math.abs(Math.hypot((p.x - 320) / 200, (p.y - 220) / 192) - 1) < 0.05)).toBe(true);
  });

  it("puts the focus in the middle and the rest on a circle, the same way every time", () => {
    const a = ringLayout("f", ["f", "a", "b", "c", "d"]);
    const b = ringLayout("f", ["f", "a", "b", "c", "d"]);
    expect(a).toEqual(b);
    expect(a.pages[0]).toEqual({ id: "f", x: 320, y: 220, side: "middle", inner: false });
    expect(a.pages).toHaveLength(5);
    // the first ring page is straight above the middle, then clockwise
    expect(a.pages[1]).toMatchObject({ id: "a", x: 320, side: "middle" });
    expect(a.pages[1]!.y).toBeLessThan(220);
    expect(a.pages[2]!.x).toBeGreaterThan(320);
    expect(a.pages[2]!.side).toBe("start");
    expect(a.pages[4]!.side).toBe("end");
  });

  it("places an overview's pages all on the circle and copes with one page and none", () => {
    expect(ringLayout(null, ["a", "b"]).pages.map((p) => p.id)).toEqual(["a", "b"]);
    expect(ringLayout(null, ["a"]).pages).toHaveLength(1);
    expect(ringLayout(null, []).pages).toEqual([]);
    expect(ringLayout("f", ["f"]).pages).toEqual([{ id: "f", x: 320, y: 220, side: "middle", inner: false }]);
  });
});
