import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { cheatSheet, envelope } from "@/test/fixtures";

import { CheatSheet, layout, sheetMarkdown } from "./CheatSheet";
import { NotesNav } from "./notesNav";

describe("CheatSheet: the wire states", () => {
  it("loading: a busy status and none of the sheet", () => {
    render(<CheatSheet block={cheatSheet("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("region", { name: "Concepts" })).not.toBeInTheDocument();
  });

  it("empty: says why in words, counting what was looked at, and is not a failure", () => {
    render(<CheatSheet block={cheatSheet("empty", { skipped: 2 })} />);
    expect(screen.getByText("No sheet could be made.")).toBeInTheDocument();
    expect(screen.getByText(/2 concepts were looked at/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert", () => {
    render(<CheatSheet block={cheatSheet("error", {}, envelope({ message: "The vault is unreadable." }))} />);
    expect(within(screen.getByRole("alert")).getByText("The vault is unreadable.")).toBeInTheDocument();
  });

  it("partial: shows what is there and says it is not final", () => {
    render(<CheatSheet block={cheatSheet("partial")} />);
    expect(screen.getByRole("region", { name: "Concepts" })).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });
});

describe("CheatSheet: ready", () => {
  it("names the focus, shows each concept with its sentence and source, and lists the connections in words", () => {
    render(<CheatSheet block={cheatSheet("ready")} />);
    expect(screen.getByRole("heading", { name: "reciprocal rank fusion" })).toBeInTheDocument();
    const concepts = within(screen.getByRole("region", { name: "Concepts" }));
    expect(concepts.getAllByRole("listitem")).toHaveLength(3);
    expect(concepts.getByText(/Dense retrieval finds passages by comparing embedding vectors/)).toBeInTheDocument();
    const connections = within(screen.getByRole("region", { name: "Connections" }));
    expect(connections.getByText("combines")).toBeInTheDocument();
    expect(connections.getByText("appears with")).toBeInTheDocument();
  });

  it("draws a diagram that has a name and says what it holds, and the same concepts are in the lists", () => {
    render(<CheatSheet block={cheatSheet("ready")} />);
    const diagram = screen.getByRole("img", { name: "Concept diagram" });
    expect(diagram).toHaveTextContent("3 concepts and 2 connections");
    expect(within(diagram).getByText("BM25")).toBeInTheDocument();
  });

  it("the layout puts the focus in the middle and is a pure function of the entries", () => {
    const entries = cheatSheet("ready").data.entries;
    const a = layout(entries, "rrf");
    const b = layout(entries, "rrf");
    expect(a.get("rrf")).toEqual({ x: 180, y: 130 });
    expect([...a.entries()]).toEqual([...b.entries()]);
  });

  it("says how many linked concepts had no stored sentence, and what a solid and a dashed line mean", () => {
    render(<CheatSheet block={cheatSheet("ready")} />);
    expect(screen.getByText(/1 linked concept had no stored sentence and is not shown/)).toBeInTheDocument();
    expect(screen.getByText(/A solid line is a relation a source states/)).toBeInTheDocument();
  });

  it("a page name opens the page when the notes screen can, and the focus is plain text", () => {
    const openPage = vi.fn();
    render(
      <NotesNav.Provider value={{ openPage }}>
        <CheatSheet block={cheatSheet("ready")} />
      </NotesNav.Provider>,
    );
    const concepts = within(screen.getByRole("region", { name: "Concepts" }));
    fireEvent.click(concepts.getByRole("button", { name: "dense retrieval" }));
    expect(openPage).toHaveBeenCalledWith("dense_retrieval");
    expect(concepts.queryByRole("button", { name: "reciprocal rank fusion" })).not.toBeInTheDocument();
  });

  it("renders the document's text as text, never as markup", () => {
    const sheet = cheatSheet("ready");
    sheet.data.citations[0]!.quote = 'A <img src=x onerror="alert(1)"> **claim** in the document.';
    const { container } = render(<CheatSheet block={sheet} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container).toHaveTextContent('<img src=x onerror="alert(1)">');
  });

  it("an entry whose citation is missing renders nothing (never a dead card)", () => {
    const sheet = cheatSheet("ready");
    sheet.data.entries[1]!.citationId = "gone";
    render(<CheatSheet block={sheet} />);
    expect(within(screen.getByRole("region", { name: "Concepts" })).getAllByRole("listitem")).toHaveLength(2);
  });

  it("the Markdown holds exactly the block's own text", () => {
    const md = sheetMarkdown(cheatSheet("ready").data);
    expect(md).toContain("# Cheat sheet: reciprocal rank fusion");
    expect(md).toContain("- **dense retrieval** (method): Dense retrieval finds passages by comparing embedding vectors.");
    expect(md).toContain("- dense retrieval combines reciprocal rank fusion");
    expect(md).toContain("- BM25 appears with reciprocal rank fusion");
  });
});
