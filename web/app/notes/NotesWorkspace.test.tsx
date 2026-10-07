// The notes screen against a mocked server: the overview, opening a page from the graph and from a link, searching, and the
// failures. The server composes everything; the screen holds only the user's choice and the last answer.

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { conceptPage, envelope, jsonResponse, layout, notesGraph } from "@/test/fixtures";

import { NotesWorkspace } from "./NotesWorkspace";

const studioOnly = layout([{ blockId: "notes-graph", panel: "studio", region: "main", order: 0 }], {
  mode: "exploration",
  panels: [
    { id: "sources", width: 0, direction: "rows", regions: [{ id: "main", size: 100 }] },
    { id: "chat", width: 40, direction: "rows", regions: [{ id: "main", size: 100 }] },
    { id: "studio", width: 60, direction: "rows", regions: [{ id: "main", size: 100 }] },
  ],
});
const pageAndGraph = layout(
  [
    { blockId: "page:self_rag", panel: "chat", region: "main", order: 0 },
    { blockId: "notes-graph", panel: "studio", region: "main", order: 0 },
  ],
  { mode: studioOnly.mode, panels: studioOnly.panels },
);

const overview = () => ({ layout: studioOnly, blocks: [notesGraph("ready")] });
const focused = () => ({
  layout: pageAndGraph,
  blocks: [{ ...conceptPage("ready"), id: "page:self_rag" }, notesGraph("ready", { focusId: "rag" })],
});

let calls: URL[];
let answer: (url: URL) => Response;

beforeEach(() => {
  calls = [];
  answer = () => jsonResponse(overview());
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      const url = new URL(input);
      calls.push(url);
      return answer(url);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("NotesWorkspace", () => {
  it("opens on the overview of the most linked pages and invites a choice", async () => {
    render(<NotesWorkspace />);
    expect(await screen.findByRole("group", { name: /Page graph of 3 pages/ })).toBeInTheDocument();
    expect(calls[0]!.pathname).toBe("/vault/notes");
    expect(calls[0]!.search).toBe("");
    expect(screen.getByText("Choose a page in the graph, or search for a concept.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Notes" })).toHaveAttribute("aria-current", "page");
  });

  it("opens a page when its name is chosen in the graph, and shows the page beside the graph", async () => {
    render(<NotesWorkspace />);
    const list = await screen.findByRole("region", { name: "Pages" });
    answer = () => jsonResponse(focused());
    fireEvent.click(within(list).getByRole("button", { name: "Self-RAG" }));
    expect(await screen.findByRole("article", { name: "Retrieval-Augmented Generation" })).toBeInTheDocument();
    expect(calls.at(-1)!.searchParams.get("page")).toBe("self_rag");
    expect(screen.queryByText("Choose a page in the graph, or search for a concept.")).not.toBeInTheDocument();
  });

  it("opens another page from a link on the page", async () => {
    answer = () => jsonResponse(focused());
    render(<NotesWorkspace />);
    const article = await screen.findByRole("article", { name: "Retrieval-Augmented Generation" });
    answer = () => jsonResponse(overview());
    fireEvent.click(within(article).getAllByRole("button", { name: "Self-RAG" })[0]!);
    await waitFor(() => expect(calls.at(-1)!.searchParams.get("page")).toBe("self_rag"));
  });

  it("searches, drops the open page, and can go back to all pages", async () => {
    render(<NotesWorkspace />);
    await screen.findByRole("group", { name: /Page graph/ });
    fireEvent.change(screen.getByRole("textbox", { name: "Search pages" }), { target: { value: "  rag " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(calls.at(-1)!.searchParams.get("query")).toBe("rag"));
    expect(calls.at(-1)!.searchParams.has("page")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "All pages" }));
    await waitFor(() => expect(calls.at(-1)!.search).toBe(""));
    expect(screen.queryByRole("button", { name: "All pages" })).not.toBeInTheDocument();
  });

  it("shows the server's reason when it cannot answer, as an alert", async () => {
    answer = () => jsonResponse(envelope({ code: "not_found", message: "The vault has no page 'x'.", retryable: false }), 404);
    render(<NotesWorkspace />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The vault has no page 'x'.");
  });

  it("says there are no pages when the vault is empty", async () => {
    answer = () => jsonResponse({ layout: studioOnly, blocks: [notesGraph("empty")] });
    render(<NotesWorkspace />);
    expect(await screen.findByText("There are no pages yet.")).toBeInTheDocument();
  });

  it("reaches no further than the notes endpoint (nothing is sent to a model)", async () => {
    render(<NotesWorkspace />);
    await screen.findByRole("group", { name: /Page graph/ });
    expect(calls.every((u) => u.pathname === "/vault/notes")).toBe(true);
  });
});
