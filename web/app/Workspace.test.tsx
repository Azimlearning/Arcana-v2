// The whole shell against a mocked server: upload, ask, and what the user sees on success and on
// every failure the Verify step names.

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TITLE, block, envelope, frame, jsonResponse, sseResponse, trace } from "@/test/fixtures";
import { useWorkspace } from "@/lib/store";

import { Workspace } from "./Workspace";

const INGESTED = { docId: "d", title: TITLE, status: "ready", chunkCount: 4, error: null };

let routes: Record<string, () => Response>;

beforeEach(() => {
  useWorkspace.setState(useWorkspace.getInitialState(), true);
  routes = {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = new URL(url).pathname;
      const route = routes[path];
      if (!route) throw new TypeError(`no mock for ${path}`);
      return route();
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

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
    await waitFor(() => expect(fetch).not.toHaveBeenCalled());
  });
});
