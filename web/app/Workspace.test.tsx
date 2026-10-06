// The whole shell against a mocked server: upload, ask, and what the user sees on success and on
// every failure the Verify step names.

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TITLE, block, comparisonGrid, envelope, frame, graphView, jsonResponse, layout, savedPattern, sourceList, sseResponse, trace, workspace } from "@/test/fixtures";
import { useWorkspace } from "@/lib/store";

import { Workspace } from "./Workspace";

const INGESTED = { docId: "d", title: TITLE, status: "ready", chunkCount: 4, error: null };

/** Mocked routes by path, or by `METHOD path` when the method matters. */
let routes: Record<string, (init?: RequestInit) => Response>;

beforeEach(() => {
  useWorkspace.setState(useWorkspace.getInitialState(), true);
  routes = {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      const route = routes[`${init?.method ?? "GET"} ${path}`] ?? routes[path];
      if (!route) throw new TypeError(`no mock for ${path}`);
      return route(init);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** The turn's blocks as the server sends them, with an optional layout after them (null: no layout is sent). */
const answerWith = (adaptive: ReturnType<typeof layout> | null) =>
  sseResponse([
    frame({ type: "block", block: block("loading") }),
    frame({ type: "block", block: block("ready") }),
    frame({ type: "block", block: sourceList("ready") }),
    frame({ type: "block", block: graphView("ready") }),
    frame({ type: "block", block: comparisonGrid("ready") }),
    ...(adaptive ? [frame({ type: "layout", layout: adaptive })] : []),
    frame({ type: "done" }),
  ]);

const places = () => [
  { blockId: "turn-1", panel: "chat" as const, order: 0 },
  { blockId: "turn-1-comparison-grid", panel: "chat" as const, order: 1 },
  { blockId: "turn-1-sources", panel: "sources" as const, order: 0 },
  { blockId: "turn-1-graph-view", panel: "studio" as const, order: 0 },
];

const researchPanels = (sources: number, chat: number, studio: number) => [
  { id: "sources" as const, width: sources },
  { id: "chat" as const, width: chat },
  { id: "studio" as const, width: studio },
];

const okStream = () =>
  sseResponse([
    frame({ type: "block", block: block("loading") }),
    frame({ type: "block", block: block("ready") }),
    frame({ type: "done" }),
  ]);

async function upload(name = "paper.pdf") {
  const file = new File(["%PDF-1.4"], name, { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText("Upload a PDF"), { target: { files: [file] } });
}

function ask(question = "How does dense retrieval compare with BM25?") {
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: question } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
}

describe("Workspace", () => {
  it("uploads a PDF and lists it as a source", async () => {
    routes["/ingest"] = () => jsonResponse(INGESTED);
    render(<Workspace />);
    await upload();
    const sources = await screen.findByLabelText("Sources", { selector: "aside" });
    expect(await within(sources).findByText(TITLE)).toBeInTheDocument();
    expect(within(sources).getByText("4 passages")).toBeInTheDocument();
  });

  it("shows why an upload failed, from the server's error envelope", async () => {
    routes["/ingest"] = () => jsonResponse(envelope({ code: "bad_request", message: "The file does not look like a PDF." }), 400);
    render(<Workspace />);
    await upload("notes.pdf");
    expect(await screen.findByRole("alert")).toHaveTextContent("The file does not look like a PDF.");
  });

  it("shows a document that ingested with status failed, with its reason", async () => {
    routes["/ingest"] = () => jsonResponse({ ...INGESTED, status: "failed", chunkCount: 0, error: "No extractable text." });
    render(<Workspace />);
    await upload();
    expect(await screen.findByText("No extractable text.")).toBeInTheDocument();
  });

  it("asking renders a cited answer that names its source document", async () => {
    routes["/chat"] = okStream;
    render(<Workspace />);
    ask();

    const answer = await screen.findByLabelText("Answer");
    expect(await within(answer).findByText(/Dense retrieval embeds passages/)).toBeInTheDocument();
    const pill = within(answer).getAllByRole("link", { name: new RegExp(`^Source c1: ${TITLE}`) })[0];
    expect(pill).toBeDefined();
    expect(within(answer).getByRole("region", { name: "Sources" })).toHaveTextContent(TITLE);
    expect(within(answer).queryByRole("status", { busy: true } as never)).toBeNull(); // the loading skeleton is gone
  });

  it("the loading block is replaced in place by the final block, not added beside it", async () => {
    routes["/chat"] = okStream;
    render(<Workspace />);
    ask();
    await screen.findByText(/Dense retrieval embeds passages/);
    expect(useWorkspace.getState().order).toEqual(["turn-1"]);
    expect(useWorkspace.getState().turn).toBe("idle");
  });

  it("the server being forced to fail renders the error state, not a blank or partial render", async () => {
    routes["/chat"] = () =>
      sseResponse([
        frame({ type: "block", block: block("loading") }),
        frame({ type: "block", block: block("error", {}, envelope({ message: "The model is unavailable." })) }),
        frame({ type: "done" }),
      ]);
    render(<Workspace />);
    ask();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The model is unavailable.");
    expect(screen.queryByText(/Dense retrieval embeds passages/)).not.toBeInTheDocument();
  });

  it("killing the API mid-stream turns the stuck loading block into the error state", async () => {
    routes["/chat"] = () => sseResponse([frame({ type: "block", block: block("loading") })], { breakAfter: true });
    render(<Workspace />);
    ask();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The connection to the server was lost.");
    expect(screen.queryByRole("status", { busy: true })).not.toBeInTheDocument(); // no skeleton left spinning
    expect(useWorkspace.getState().turn).toBe("failed");
  });

  it("an unreachable API renders the error state too", async () => {
    // no route registered: the mocked fetch rejects, as it does when the server is down
    render(<Workspace />);
    ask();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
  });

  it("a request the server rejects shows its message", async () => {
    routes["/chat"] = () => jsonResponse(envelope({ code: "bad_request", message: "The message is empty.", retryable: false }), 400);
    render(<Workspace />);
    ask("   x  ");
    expect(await screen.findByRole("alert")).toHaveTextContent("The message is empty.");
  });

  it("offers the trace after a finished turn, and shows its hops when opened", async () => {
    routes["/chat"] = okStream;
    routes["/turns/turn-1/trace"] = () => jsonResponse(trace());
    render(<Workspace />);
    ask();
    await screen.findByText(/Dense retrieval embeds passages/);
    fireEvent.click(await screen.findByRole("button", { name: "Show how this was answered" }));
    expect(await screen.findByText(/1\. orchestrator/)).toBeInTheDocument();
    expect(screen.getByText(/2\. research/)).toBeInTheDocument();
    expect(screen.getByText(/3\. fact checker/)).toBeInTheDocument();
  });

  it("shows a comparison beneath the answer and still opens the trace of the turn, not of the extra block", async () => {
    routes["/chat"] = () =>
      sseResponse([
        frame({ type: "block", block: block("loading") }),
        frame({ type: "block", block: block("ready") }),
        frame({ type: "block", block: comparisonGrid("ready") }),
        frame({ type: "done" }),
      ]);
    routes["/turns/turn-1/trace"] = () => jsonResponse(trace());
    render(<Workspace />);
    ask();
    expect(await screen.findByRole("table")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Show how this was answered" }));
    expect(await screen.findByText(/1\. orchestrator/)).toBeInTheDocument(); // the trace of "turn-1", the answer's id
  });

  it("opens on Basic with the source list before any question", async () => {
    routes["/workspace"] = () => jsonResponse(workspace());
    render(<Workspace />);
    const sources = screen.getByRole("complementary", { name: "Sources" });
    expect(await within(sources).findByText("Stored Paper")).toBeInTheDocument();
    expect(within(sources).getByText("7 passages")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Basic" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Adaptive" })).toBeDisabled();
    expect(screen.getByText("Adaptive is available after your first answer.")).toBeInTheDocument();
  });

  it("opens on the fixed fallback layout when /workspace cannot be read, still usable for uploads and questions", async () => {
    routes["/workspace"] = () => jsonResponse({ nonsense: true });
    render(<Workspace />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.getByLabelText("Upload a PDF")).toBeInTheDocument();
    expect(screen.getByRole("main", { name: "Chat" })).toHaveStyle({ flexGrow: "60" });
  });

  it("applies the layout's widths as flex-grow values, and a hidden panel is aria-hidden and inert", async () => {
    routes["/workspace"] = () => jsonResponse(workspace());
    const allInChat = places().map((p, i) => ({ ...p, panel: "chat" as const, order: i }));
    routes["/chat"] = () => answerWith(layout(allInChat, { panels: researchPanels(0, 100, 0) }));
    render(<Workspace />);
    ask();
    await screen.findByText(/Dense retrieval embeds passages/);
    await waitFor(() => expect(screen.getByRole("button", { name: "Adaptive" })).toHaveAttribute("aria-pressed", "true"));
    const chat = screen.getByRole("main", { name: "Chat" });
    expect(chat).toHaveStyle({ flexGrow: "100" });
    const sources = document.querySelector('[data-panel="sources"]')!;
    expect(sources).toHaveStyle({ flexGrow: "0" });
    expect(sources).toHaveAttribute("aria-hidden", "true");
    expect(sources).toHaveAttribute("inert");
    expect(chat).not.toHaveAttribute("aria-hidden");
    expect(chat).not.toHaveAttribute("inert");
  });

  it("shows each block in the panel the adaptive layout places it in, and in order within a panel", async () => {
    routes["/workspace"] = () => jsonResponse(workspace());
    routes["/chat"] = () => answerWith(layout(places(), { panels: researchPanels(20, 45, 35) }));
    render(<Workspace />);
    ask();
    await screen.findByText(/Dense retrieval embeds passages/);
    const studio = document.querySelector('[data-panel="studio"]') as HTMLElement;
    expect(await within(studio).findByRole("group", { name: /Graph of 3 concepts/ })).toBeInTheDocument();
    const sources = document.querySelector('[data-panel="sources"]') as HTMLElement;
    expect(within(sources).getByText("BM25 in Practice")).toBeInTheDocument(); // the turn's list replaced the workspace's
    expect(within(sources).queryByText("Stored Paper")).not.toBeInTheDocument();
    const chat = screen.getByLabelText("Answer");
    const text = chat.textContent ?? "";
    expect(text.indexOf("Dense retrieval embeds passages")).toBeLessThan(text.indexOf("Comparison of"));
    expect(within(chat).queryByRole("group", { name: /Graph of/ })).not.toBeInTheDocument();
  });

  it("in Basic every turn block is stacked in the answer column, and the turn's source list is not repeated", async () => {
    routes["/workspace"] = () => jsonResponse(workspace());
    routes["/chat"] = () => answerWith(null);
    render(<Workspace />);
    ask();
    await screen.findByText(/Dense retrieval embeds passages/);
    const chat = screen.getByLabelText("Answer");
    expect(await within(chat).findByRole("group", { name: /Graph of/ })).toBeInTheDocument();
    expect(within(chat).queryByText("BM25 in Practice")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Basic" })).toHaveAttribute("aria-pressed", "true");
  });

  it("ignores a layout it cannot read, an unknown version included, and stays on Basic", async () => {
    routes["/workspace"] = () => jsonResponse(workspace());
    for (const bad of [layout(places(), { version: 2 }), layout(places(), { panels: researchPanels(20, 45, 30) })]) {
      cleanup();
      useWorkspace.setState(useWorkspace.getInitialState(), true);
      routes["/chat"] = () => answerWith(bad);
      render(<Workspace />);
      ask();
      await screen.findByText(/Dense retrieval embeds passages/);
      expect(screen.getByRole("button", { name: "Adaptive" })).toBeDisabled();
      expect(within(screen.getByLabelText("Answer")).getByRole("group", { name: /Graph of/ })).toBeInTheDocument();
    }
  });

  it("a placement for a block the client does not have is ignored, and an unplaced block is shown in chat", async () => {
    routes["/workspace"] = () => jsonResponse(workspace());
    const partial = layout(
      [
        { blockId: "turn-1", panel: "chat", order: 0 },
        { blockId: "nobody", panel: "studio", order: 0 },
      ],
      { panels: researchPanels(20, 45, 35) },
    );
    routes["/chat"] = () => answerWith(partial);
    render(<Workspace />);
    ask();
    await screen.findByText(/Dense retrieval embeds passages/);
    const chat = screen.getByLabelText("Answer");
    // the graph view was not placed by the layout, so it falls to the answer column; "nobody" shows nothing anywhere
    expect(await within(chat).findByRole("group", { name: /Graph of/ })).toBeInTheDocument();
  });

  it("adaptive takes over by itself after the first answer; the user can pin Basic, and a later answer does not override it", async () => {
    routes["/workspace"] = () => jsonResponse(workspace());
    routes["/chat"] = () => answerWith(layout(places(), { panels: researchPanels(20, 45, 35) }));
    render(<Workspace />);
    ask();
    await waitFor(() => expect(screen.getByRole("button", { name: "Adaptive" })).toHaveAttribute("aria-pressed", "true"));

    fireEvent.click(screen.getByRole("button", { name: "Basic" })); // pins Basic
    expect(screen.getByRole("button", { name: "Basic" })).toHaveAttribute("aria-pressed", "true");
    expect(useWorkspace.getState().pinned).toBe(true);
    expect(within(screen.getByLabelText("Answer")).getByRole("group", { name: /Graph of/ })).toBeInTheDocument();

    ask("A second question?");
    await waitFor(() => expect(useWorkspace.getState().layouts.adaptive).not.toBeNull());
    expect(screen.getByRole("button", { name: "Basic" })).toHaveAttribute("aria-pressed", "true"); // not overridden
    expect(screen.getByRole("button", { name: "Adaptive" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Adaptive" })); // un-pins
    expect(screen.getByRole("button", { name: "Adaptive" })).toHaveAttribute("aria-pressed", "true");
    expect(useWorkspace.getState().pinned).toBe(false);
  });

  it("a layout that arrives before the blocks is applied to them as they arrive", async () => {
    routes["/workspace"] = () => jsonResponse(workspace());
    routes["/chat"] = () =>
      sseResponse([
        frame({ type: "layout", layout: layout(places(), { panels: researchPanels(20, 45, 35) }) }),
        frame({ type: "block", block: block("loading") }),
        frame({ type: "block", block: block("ready") }),
        frame({ type: "block", block: graphView("ready") }),
        frame({ type: "done" }),
      ]);
    render(<Workspace />);
    ask();
    const studio = document.querySelector('[data-panel="studio"]') as HTMLElement;
    expect(await within(studio).findByRole("group", { name: /Graph of/ })).toBeInTheDocument();
  });

  it("uploading refreshes the source list from the server", async () => {
    let stored = [{ docId: "d0", title: "Stored Paper", chunkCount: 7 }];
    routes["/workspace"] = () => jsonResponse(workspace(stored));
    routes["/ingest"] = () => {
      stored = [...stored, { docId: "d", title: TITLE, chunkCount: 4 }];
      return jsonResponse(INGESTED);
    };
    render(<Workspace />);
    const sources = screen.getByRole("complementary", { name: "Sources" });
    await within(sources).findByText("Stored Paper");
    await upload();
    await waitFor(() => expect(within(sources).getAllByText(TITLE)).toHaveLength(1)); // listed once, not also as a local row
    expect(within(sources).getByText("4 passages")).toBeInTheDocument();
    expect(within(sources).getByText("Stored Paper")).toBeInTheDocument();
  });

  it("offers the trace of a turn that ended in an error too, and says so if the server has none", async () => {
    routes["/chat"] = () => sseResponse([frame({ type: "block", block: block("loading") })], { breakAfter: true });
    routes["/turns/turn-1/trace"] = () =>
      jsonResponse(envelope({ code: "not_found", message: "No trace for that turn.", retryable: false }), 404);
    render(<Workspace />);
    ask();
    await screen.findByText("The connection to the server was lost.");
    fireEvent.click(await screen.findByRole("button", { name: "Show how this was answered" }));
    expect(await screen.findByText("No trace for that turn.")).toBeInTheDocument();
  });

  it("does not offer a trace while the answer is still streaming", async () => {
    routes["/chat"] = () => new Response(new ReadableStream({ start() {} }), { status: 200 }); // never ends
    render(<Workspace />);
    ask();
    await waitFor(() => expect(useWorkspace.getState().turn).toBe("streaming"));
    expect(screen.queryByRole("button", { name: /how this was answered/i })).not.toBeInTheDocument();
  });

  it("an empty answer says nothing was found, and a new question starts a fresh panel", async () => {
    routes["/chat"] = () =>
      sseResponse([
        frame({ type: "block", block: block("loading") }),
        frame({ type: "block", block: block("empty") }),
        frame({ type: "done" }),
      ]);
    render(<Workspace />);
    ask();
    expect(await screen.findByText("No evidence found in your documents.")).toBeInTheDocument();

    routes["/chat"] = okStream;
    ask("another question");
    await screen.findByText(/Dense retrieval embeds passages/);
    expect(screen.queryByText("No evidence found in your documents.")).not.toBeInTheDocument();
  });

  it("does not send an empty question", async () => {
    render(<Workspace />);
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    await waitFor(() => expect(fetch).toHaveBeenCalled()); // the workspace loads on open
    const chatCalls = vi.mocked(fetch).mock.calls.filter(([url]) => String(url).includes("/chat"));
    expect(chatCalls).toEqual([]); // but no question was sent
  });

  describe("saved views", () => {
    const openList = async () => {
      fireEvent.click(await screen.findByText(/Saved views \(/));
    };

    /** The apply stream the server sends for a saved graph: one block (an apply id) and its layout. */
    const appliedStream = () =>
      sseResponse([
        frame({ type: "block", block: { ...graphView("ready"), id: "apply-9-graph-view" } }),
        frame({
          type: "layout",
          layout: layout([{ blockId: "apply-9-graph-view", panel: "studio", order: 0 }], {
            panels: [
              { id: "sources", width: 0 },
              { id: "chat", width: 40 },
              { id: "studio", width: 60 },
            ],
            mode: "exploration",
          }),
        }),
        frame({ type: "done" }),
      ]);

    it("lists the user's saved views, with their names and kinds", async () => {
      routes["/patterns"] = () => jsonResponse({ patterns: [savedPattern(), savedPattern({ id: "p-2", name: "Comparison", templateId: "ComparisonGrid" })] });
      render(<Workspace />);
      await openList();
      const items = within(await screen.findByRole("list", { name: "Saved views" })).getAllByRole("listitem");
      expect(items).toHaveLength(2);
      expect(items[0]).toHaveTextContent("Dense vs BM25");
      expect(items[0]).toHaveTextContent("Connection graph");
      expect(items[1]).toHaveTextContent("Document comparison");
    });

    it("shows a saved view again through the usual block and layout path, asking no question", async () => {
      routes["/patterns"] = () => jsonResponse({ patterns: [savedPattern()] });
      routes["POST /patterns/p-1/apply"] = appliedStream;
      render(<Workspace />);
      await openList();
      fireEvent.click(await screen.findByRole("button", { name: "Show Dense vs BM25" }));
      const studio = document.querySelector('[data-panel="studio"]') as HTMLElement;
      expect(await within(studio).findByRole("group", { name: /Graph of/ })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Adaptive" })).toHaveAttribute("aria-pressed", "true"); // its layout took over
      const calls = vi.mocked(fetch).mock.calls.map(([url]) => new URL(String(url)).pathname);
      expect(calls).toContain("/patterns/p-1/apply");
      expect(calls).not.toContain("/chat");
    });

    it("says in plain words why a refused view cannot be shown, and shows nothing from it", async () => {
      routes["/patterns"] = () => jsonResponse({ patterns: [savedPattern()] });
      const refusal = envelope({ code: "pattern_refused", message: "This saved view cannot be shown.", retryable: false, issues: [{ path: "document_missing", message: "x" }] });
      routes["POST /patterns/p-1/apply"] = () => jsonResponse(refusal, 409);
      render(<Workspace />);
      await openList();
      fireEvent.click(await screen.findByRole("button", { name: "Show Dense vs BM25" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("A document this view needs is no longer in your library.");
      expect(screen.queryByRole("group", { name: /Graph of/ })).not.toBeInTheDocument();
      expect(useWorkspace.getState().order).toEqual([]);
    });

    it("checks a view again when its layout moved on, then shows it", async () => {
      routes["GET /patterns"] = () => jsonResponse({ patterns: [savedPattern()] });
      const stale = envelope({ code: "pattern_refused", message: "This saved view cannot be shown.", retryable: false, issues: [{ path: "template_changed", message: "x" }] });
      let verified = false;
      routes["POST /patterns/p-1/apply"] = () => (verified ? appliedStream() : jsonResponse(stale, 409));
      routes["POST /patterns/p-1/reverify"] = () => {
        verified = true;
        return jsonResponse(savedPattern({ state: "verified", templateVersion: 2 }));
      };
      render(<Workspace />);
      await openList();
      fireEvent.click(await screen.findByRole("button", { name: "Show Dense vs BM25" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(/older version.*checked again/);
      fireEvent.click(screen.getByRole("button", { name: "Check this view again" }));
      const studio = document.querySelector('[data-panel="studio"]') as HTMLElement;
      expect(await within(studio).findByRole("group", { name: /Graph of/ })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Check this view again" })).not.toBeInTheDocument();
    });

    it("does not offer to check again a view that was refused for another reason", async () => {
      routes["GET /patterns"] = () => jsonResponse({ patterns: [savedPattern()] });
      const gone = envelope({ code: "pattern_refused", message: "x", retryable: false, issues: [{ path: "document_missing", message: "x" }] });
      routes["POST /patterns/p-1/apply"] = () => jsonResponse(gone, 409);
      render(<Workspace />);
      await openList();
      fireEvent.click(await screen.findByRole("button", { name: "Show Dense vs BM25" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("no longer in your library");
      expect(screen.queryByRole("button", { name: "Check this view again" })).not.toBeInTheDocument();
    });

    it("deletes a saved view and refreshes the list", async () => {
      let items = [savedPattern(), savedPattern({ id: "p-2", name: "Second" })];
      routes["GET /patterns"] = () => jsonResponse({ patterns: items });
      routes["DELETE /patterns/p-1"] = () => {
        items = items.filter((p) => p.id !== "p-1");
        return new Response(null, { status: 204 });
      };
      render(<Workspace />);
      await openList();
      fireEvent.click(await screen.findByRole("button", { name: "Delete Dense vs BM25" }));
      await waitFor(() => expect(screen.queryByRole("button", { name: "Show Dense vs BM25" })).not.toBeInTheDocument());
      expect(screen.getByRole("button", { name: "Show Second" })).toBeInTheDocument();
    });

    it("offers Save this view on a finished answer's graph, and sends the turn and the kind to the server", async () => {
      routes["/chat"] = () => answerWith(layout(places(), { panels: researchPanels(20, 45, 35) }));
      let body: unknown = null;
      routes["POST /patterns"] = (init) => {
        body = JSON.parse(String(init?.body));
        return jsonResponse(savedPattern());
      };
      routes["GET /patterns"] = () => jsonResponse({ patterns: [] });
      render(<Workspace />);
      ask();
      const studio = document.querySelector('[data-panel="studio"]') as HTMLElement;
      await within(studio).findByRole("group", { name: /Graph of/ });
      fireEvent.click(await within(studio).findByRole("button", { name: "Save this view" }));
      fireEvent.change(within(studio).getByLabelText("Name"), { target: { value: "My graph" } });
      fireEvent.click(within(studio).getByRole("button", { name: "Save" }));
      expect(await within(studio).findByText(/Saved\. You will find it under Saved views/)).toBeInTheDocument();
      expect(body).toEqual({ turnId: "turn-1", templateId: "GraphView", name: "My graph" });
    });

    it("shows the server's reason when a view cannot be saved", async () => {
      routes["/chat"] = () => answerWith(layout(places(), { panels: researchPanels(20, 45, 35) }));
      routes["POST /patterns"] = () => jsonResponse(envelope({ code: "bad_request", message: "That view was not verified, so it cannot be saved.", retryable: false }), 400);
      render(<Workspace />);
      ask();
      const studio = document.querySelector('[data-panel="studio"]') as HTMLElement;
      fireEvent.click(await within(studio).findByRole("button", { name: "Save this view" }));
      fireEvent.click(within(studio).getByRole("button", { name: "Save" }));
      expect(await within(studio).findByRole("alert")).toHaveTextContent("That view was not verified, so it cannot be saved.");
    });

    it("does not offer to save the answer itself, a loading block, or a view that was applied from a saved one", async () => {
      routes["/chat"] = () => answerWith(layout(places(), { panels: researchPanels(20, 45, 35) }));
      render(<Workspace />);
      ask();
      await screen.findByText(/Dense retrieval embeds passages/);
      const answer = screen.getByLabelText("Answer");
      await waitFor(() => expect(within(answer).getAllByRole("button", { name: "Save this view" })).toHaveLength(1)); // the grid, in chat
      cleanup();

      useWorkspace.setState(useWorkspace.getInitialState(), true);
      routes["/patterns"] = () => jsonResponse({ patterns: [savedPattern()] });
      routes["POST /patterns/p-1/apply"] = appliedStream;
      render(<Workspace />);
      await openList();
      fireEvent.click(await screen.findByRole("button", { name: "Show Dense vs BM25" }));
      const studio = document.querySelector('[data-panel="studio"]') as HTMLElement;
      await within(studio).findByRole("group", { name: /Graph of/ });
      expect(within(studio).queryByRole("button", { name: "Save this view" })).not.toBeInTheDocument();
    });
  });
});

