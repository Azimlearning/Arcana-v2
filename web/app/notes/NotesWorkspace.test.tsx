// The notes screen against a mocked server: the overview, opening a page from the graph and from a link, searching, and the
// failures. The server composes everything; the screen holds only the user's choice and the last answer.

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { conceptPage, envelope, jsonResponse, layout, notesGraph, quizAnswer, quizCard } from "@/test/fixtures";

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

const quizAndGraph = layout(
  [
    { blockId: "quiz", panel: "chat", region: "main", order: 0 },
    { blockId: "notes-graph", panel: "studio", region: "main", order: 0 },
  ],
  { mode: studioOnly.mode, panels: studioOnly.panels },
);
const quiz = () => ({ layout: quizAndGraph, blocks: [quizCard("ready"), notesGraph("ready")] });

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

  it("records a rating and shows the page again with it, without blanking the page meanwhile", async () => {
    const posted: unknown[] = [];
    answer = () => jsonResponse(focused());
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string, init?: RequestInit) => {
        const url = new URL(input);
        if (url.pathname === "/learner/events") {
          posted.push(JSON.parse(String(init?.body)));
          return jsonResponse({ pageId: "rag", mastery: { score: 0.6667, events: 1 } });
        }
        calls.push(url);
        return answer(url);
      }),
    );
    render(<NotesWorkspace />);
    const article = await screen.findByRole("article", { name: "Retrieval-Augmented Generation" });
    expect(screen.getByRole("region", { name: "Your mastery" })).toHaveTextContent("You have not rated this concept yet.");
    const rated = focused();
    (rated.blocks[0] as ReturnType<typeof conceptPage>).data.mastery = { score: 0.6667, events: 1 };
    answer = () => jsonResponse(rated);
    const before = calls.length;
    fireEvent.click(within(article).getByRole("button", { name: "I know this" }));
    await waitFor(() => expect(posted).toEqual([{ pageId: "rag", signal: "know" }]));
    await waitFor(() => expect(screen.getByRole("region", { name: "Your mastery" })).toHaveTextContent("Getting there (67 percent, from 1 rating or answer)."));
    expect(calls.length).toBe(before + 1); // the same page, fetched once more
    expect(screen.queryByText("Opening the notes…")).not.toBeInTheDocument();
  });

  it("reaches no further than the notes endpoint (nothing is sent to a model)", async () => {
    render(<NotesWorkspace />);
    await screen.findByRole("group", { name: /Page graph/ });
    expect(calls.every((u) => u.pathname === "/vault/notes")).toBe(true);
  });
});

describe("NotesWorkspace: the quiz", () => {
  it("'Quiz me' asks the server for a quiz and shows it beside the graph", async () => {
    render(<NotesWorkspace />);
    await screen.findByRole("group", { name: /Page graph/ });
    answer = (url) => jsonResponse(url.pathname === "/vault/quiz" ? quiz() : overview());
    fireEvent.click(screen.getByRole("button", { name: "Quiz me" }));
    expect(await screen.findByRole("region", { name: "Quiz questions" })).toBeInTheDocument();
    expect(calls.at(-1)!.pathname).toBe("/vault/quiz");
    expect(calls.at(-1)!.search).toBe("");
    expect(screen.getByRole("group", { name: /Page graph/ })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "dense retrieval" })).toHaveLength(1); // the choices are buttons here
  });

  it("'All pages' leaves the quiz and returns to the notes", async () => {
    render(<NotesWorkspace />);
    await screen.findByRole("group", { name: /Page graph/ });
    answer = (url) => jsonResponse(url.pathname === "/vault/quiz" ? quiz() : overview());
    fireEvent.click(screen.getByRole("button", { name: "Quiz me" }));
    await screen.findByRole("region", { name: "Quiz questions" });
    fireEvent.click(screen.getByRole("button", { name: "All pages" }));
    expect(await screen.findByText("Choose a page in the graph, or search for a concept.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Quiz questions" })).not.toBeInTheDocument();
    expect(calls.at(-1)!.pathname).toBe("/vault/notes");
  });

  it("on an open page it offers a quiz about that page", async () => {
    render(<NotesWorkspace />);
    const list = await screen.findByRole("region", { name: "Pages" });
    answer = () => jsonResponse(focused());
    fireEvent.click(within(list).getByRole("button", { name: "Self-RAG" }));
    await screen.findByRole("article", { name: "Retrieval-Augmented Generation" });
    answer = (url) => jsonResponse(url.pathname === "/vault/quiz" ? quiz() : focused());
    fireEvent.click(screen.getByRole("button", { name: "Quiz me on this page" }));
    await screen.findByRole("region", { name: "Quiz questions" });
    expect(calls.at(-1)!.pathname).toBe("/vault/quiz");
    expect(calls.at(-1)!.searchParams.get("page")).toBe("self_rag");
  });

  it("checks a choice on the server, keeps the questions as they are and shows the graph around the answered concept", async () => {
    const posted: unknown[] = [];
    const first = quizCard("ready");
    const moved = {
      layout: quizAndGraph,
      blocks: [
        { ...first, data: { ...first.data, items: [{ ...first.data.items[0]!, id: "claim-7~bm25", text: "_____ is a different question now." }] } },
        notesGraph("ready", {
          nodes: [{ id: "rag", label: "Retrieval-Augmented Generation", kind: "concept", passages: 2, documents: 2, degree: 2, mastery: 0.6667 }],
          edges: [],
        }),
      ],
    };
    let quizCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string, init?: RequestInit) => {
        const url = new URL(input);
        if (url.pathname === "/quiz/answer") {
          posted.push(JSON.parse(String(init?.body)));
          return jsonResponse(quizAnswer());
        }
        calls.push(url);
        if (url.pathname === "/vault/quiz") return jsonResponse(++quizCalls === 1 ? quiz() : moved);
        if (url.searchParams.get("page") === "dense_retrieval") return jsonResponse(moved); // the graph around the concept just answered
        return jsonResponse(overview());
      }),
    );
    render(<NotesWorkspace />);
    await screen.findByRole("group", { name: /Page graph/ });
    fireEvent.click(screen.getByRole("button", { name: "Quiz me" }));
    const question = (await screen.findAllByRole("listitem")).find((li) => li.textContent?.includes("Question 1 of 2"))!;
    fireEvent.click(within(question).getByRole("button", { name: "dense retrieval" }));
    expect(await within(question).findByText("Correct.")).toBeInTheDocument();
    expect(posted).toEqual([{ itemId: "claim-1~dense_retrieval", chosenId: "dense_retrieval" }]);
    await waitFor(() => expect(screen.getByRole("group", { name: /Page graph of 1 pages/ })).toBeInTheDocument());
    expect(calls.at(-1)!.pathname).toBe("/vault/notes");
    expect(calls.at(-1)!.searchParams.get("page")).toBe("dense_retrieval"); // the graph is asked for around the answered concept
    expect(screen.getByRole("region", { name: "Pages" })).toHaveTextContent(/getting there/i);
    expect(screen.queryByText(/is a different question now/)).not.toBeInTheDocument(); // the questions did not change under the learner
    expect(screen.getByText(/Question 1 of 2/)).toBeInTheDocument();
  });

  it("'More questions' fetches a new quiz", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string, init?: RequestInit) => {
        const url = new URL(input);
        if (url.pathname === "/quiz/answer") {
          const body = JSON.parse(String(init?.body)) as { itemId: string };
          return jsonResponse(quizAnswer({ itemId: body.itemId }));
        }
        calls.push(url);
        return jsonResponse(url.pathname === "/vault/quiz" ? quiz() : overview());
      }),
    );
    render(<NotesWorkspace />);
    await screen.findByRole("group", { name: /Page graph/ });
    fireEvent.click(screen.getByRole("button", { name: "Quiz me" }));
    const items = (await screen.findAllByRole("listitem")).filter((li) => /Question \d of 2/.test(li.textContent ?? ""));
    for (const item of items) {
      fireEvent.click(within(item).getAllByRole("button")[0]!);
      await within(item).findByText(/Correct\.|Not quite/);
    }
    const before = calls.filter((u) => u.pathname === "/vault/quiz").length;
    fireEvent.click(await screen.findByRole("button", { name: "More questions" }));
    await waitFor(() => expect(calls.filter((u) => u.pathname === "/vault/quiz").length).toBeGreaterThan(before));
  });

  it("reaches no further than the vault's endpoints (nothing is sent to a model)", async () => {
    render(<NotesWorkspace />);
    await screen.findByRole("group", { name: /Page graph/ });
    answer = (url) => jsonResponse(url.pathname === "/vault/quiz" ? quiz() : overview());
    fireEvent.click(screen.getByRole("button", { name: "Quiz me" }));
    await screen.findByRole("region", { name: "Quiz questions" });
    expect(calls.every((u) => u.pathname.startsWith("/vault/"))).toBe(true);
  });
});
