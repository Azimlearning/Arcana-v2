import type { WorkspaceResponse } from "@arcana/schema";
import { describe, expect, it, vi } from "vitest";

import { envelope, jsonResponse, layout, quizAnswer, savedPattern, sourceList } from "@/test/fixtures";

import { answerQuiz, deletePattern, fetchLint, fetchNotes, fetchQuiz, fetchWorkspace, recordLearnerEvent, isSavedPattern, listPatterns, reverifyPattern, savePattern } from "./api";

const prebuilt = layout([{ blockId: "workspace-sources", panel: "sources", region: "main" as const, order: 0 }], {
  origin: "prebuilt",
  mode: "basic",
  panels: [
    { id: "sources", width: 20, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] },
    { id: "chat", width: 60, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] },
    { id: "studio", width: 20, direction: "rows" as const, regions: [{ id: "main" as const, size: 100 }] },
  ],
});
const GOOD: WorkspaceResponse = { layout: prebuilt, blocks: [{ ...sourceList("ready"), id: "workspace-sources" }] };

const get = (response: Response | (() => Promise<Response>)) => {
  const fetchImpl = vi.fn(typeof response === "function" ? response : async () => response);
  return fetchWorkspace({ fetchImpl: fetchImpl as unknown as typeof fetch, baseUrl: "http://api" }).then((result) => ({
    result,
    fetchImpl,
  }));
};

describe("fetchWorkspace", () => {
  it("returns the layout and blocks of a well-formed response, from GET /workspace", async () => {
    const { result, fetchImpl } = await get(jsonResponse(GOOD));
    expect(result).toEqual({ ok: true, workspace: GOOD });
    expect(String((fetchImpl.mock.calls[0] as unknown[])[0])).toBe("http://api/workspace");
  });

  it("is an error state for a body that is not a workspace, never a half-rendered one", async () => {
    const bad: unknown[] = [
      null,
      "workspace",
      {},
      { layout: prebuilt },
      { blocks: GOOD.blocks },
      { layout: { ...prebuilt, version: 3 }, blocks: GOOD.blocks }, // a layout this client cannot read
      { layout: prebuilt, blocks: [{ type: "SourceList" }] }, // a block with no id, meta or data
      { layout: prebuilt, blocks: [null] },
    ];
    for (const body of bad) {
      const { result } = await get(jsonResponse(body));
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error.retryable).toBe(false);
    }
  });

  it("is an error state for a body that is not JSON", async () => {
    const { result } = await get(new Response("<html>oops</html>", { status: 200 }));
    expect(result.ok).toBe(false);
  });

  it("returns the server's own error envelope for a failed request", async () => {
    const failure = envelope({ code: "internal", message: "The workspace could not be built.", retryable: false });
    const { result } = await get(jsonResponse(failure, 500));
    expect(result).toEqual({ ok: false, error: failure });
  });

  it("is a retryable error when the server cannot be reached", async () => {
    const { result } = await get(() => Promise.reject(new TypeError("failed to fetch")));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.retryable).toBe(true);
  });
});


const opts = (response: Response | (() => Promise<Response>)) => {
  const fetchImpl = vi.fn(typeof response === "function" ? response : async () => response);
  return { fetchImpl: fetchImpl as unknown as typeof fetch, baseUrl: "http://api", spy: fetchImpl };
};

describe("saved views", () => {
  it("lists the user's patterns from GET /patterns", async () => {
    const { spy, ...o } = opts(jsonResponse({ patterns: [savedPattern(), savedPattern({ id: "p-2", state: "verified", lastUsedAt: "2026-10-07T11:00:00+00:00" })] }));
    const result = await listPatterns(o);
    expect(result.ok && result.patterns.map((p) => p.id)).toEqual(["p-1", "p-2"]);
    expect(String((spy.mock.calls[0] as unknown[])[0])).toBe("http://api/patterns");
  });

  it("refuses a body that is not a list of patterns, with a reason", async () => {
    const bad: unknown[] = [
      null,
      {},
      { patterns: "p" },
      { patterns: [{ id: "p" }] },
      { patterns: [{ ...savedPattern(), state: "pending" }] }, // a state this client does not know
      { patterns: [{ ...savedPattern(), layoutMode: "wide" }] },
      { patterns: [{ ...savedPattern(), params: [{ key: "entities", values: [3] }] }] },
      { patterns: [{ ...savedPattern(), templateVersion: 1.5 }] },
    ];
    for (const body of bad) {
      const { spy, ...o } = opts(jsonResponse(body));
      const result = await listPatterns(o);
      expect(result.ok, JSON.stringify(body)).toBe(false);
      void spy;
    }
  });

  it("saves a view with a POST and returns the pattern the server made", async () => {
    const { spy, ...o } = opts(jsonResponse(savedPattern()));
    const result = await savePattern({ turnId: "turn-1", templateId: "GraphView", name: "Dense vs BM25" }, o);
    expect(result).toEqual({ ok: true, pattern: savedPattern() });
    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api/patterns");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ turnId: "turn-1", templateId: "GraphView", name: "Dense vs BM25" });
  });

  it("returns the server's refusal as its error envelope", async () => {
    const refusal = envelope({ code: "bad_request", message: "That view was not verified, so it cannot be saved.", retryable: false });
    const { spy, ...o } = opts(jsonResponse(refusal, 400));
    void spy;
    expect(await savePattern({ turnId: "t", templateId: "GraphView", name: "n" }, o)).toEqual({ ok: false, error: refusal });
  });

  it("deletes by id, encoding it, and reports a failure", async () => {
    const ok = opts(new Response(null, { status: 204 }));
    expect(await deletePattern("a/b", { fetchImpl: ok.fetchImpl, baseUrl: ok.baseUrl })).toEqual({ ok: true });
    const [url, init] = ok.spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api/patterns/a%2Fb");
    expect(init.method).toBe("DELETE");

    const missing = envelope({ code: "not_found", message: "No saved view has that id.", retryable: false });
    const gone = opts(jsonResponse(missing, 404));
    expect(await deletePattern("x", { fetchImpl: gone.fetchImpl, baseUrl: gone.baseUrl })).toEqual({ ok: false, error: missing });
  });

  it("is a retryable error when the server cannot be reached", async () => {
    const down = opts(() => Promise.reject(new TypeError("failed to fetch")));
    for (const result of [await listPatterns(down), await savePattern({ turnId: "t", templateId: "g", name: "n" }, down), await deletePattern("x", down)]) {
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error.retryable).toBe(true);
    }
  });

  it("re-verifies a view with a POST and returns the updated pattern, or the server's refusal", async () => {
    const ok = opts(jsonResponse(savedPattern({ state: "verified", templateVersion: 2 })));
    const result = await reverifyPattern("p/1", { fetchImpl: ok.fetchImpl, baseUrl: ok.baseUrl });
    expect(result.ok && result.pattern.state).toBe("verified");
    const [url, init] = ok.spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api/patterns/p%2F1/reverify");
    expect(init.method).toBe("POST");

    const refusal = envelope({ code: "pattern_refused", message: "x", retryable: false, issues: [{ path: "precondition_not_met", message: "m" }] });
    const no = opts(jsonResponse(refusal, 409));
    expect(await reverifyPattern("p", { fetchImpl: no.fetchImpl, baseUrl: no.baseUrl })).toEqual({ ok: false, error: refusal });
    const bad = opts(jsonResponse({ nonsense: true }));
    expect((await reverifyPattern("p", { fetchImpl: bad.fetchImpl, baseUrl: bad.baseUrl })).ok).toBe(false);
  });

  it("recognises a pattern's shape", () => {
    expect(isSavedPattern(savedPattern())).toBe(true);
    expect(isSavedPattern({ ...savedPattern(), lastUsedAt: 3 })).toBe(false);
  });
});


describe("fetchNotes", () => {
  const ask = (params: Parameters<typeof fetchNotes>[0], response: Response) => {
    const fetchImpl = vi.fn(async () => response);
    return fetchNotes(params, { fetchImpl: fetchImpl as unknown as typeof fetch, baseUrl: "http://api" }).then((result) => ({
      result,
      url: String((fetchImpl.mock.calls[0] as unknown[])[0]),
    }));
  };

  it("asks GET /vault/notes with only the choices that were made, trimmed and encoded", async () => {
    expect((await ask({}, jsonResponse(GOOD))).url).toBe("http://api/vault/notes");
    expect((await ask({ page: "self_rag" }, jsonResponse(GOOD))).url).toBe("http://api/vault/notes?page=self_rag");
    expect((await ask({ query: "  graph rag " }, jsonResponse(GOOD))).url).toBe("http://api/vault/notes?query=graph+rag");
    expect((await ask({ page: "a b", query: "" }, jsonResponse(GOOD))).url).toBe("http://api/vault/notes?page=a+b");
  });

  it("returns the layout and blocks of a well-formed response", async () => {
    expect((await ask({}, jsonResponse(GOOD))).result).toEqual({ ok: true, workspace: GOOD });
  });

  it("is an error state for a body that is not a view, never a half-drawn one", async () => {
    for (const body of [null, "x", {}, { layout: prebuilt }, { layout: prebuilt, blocks: [{ type: "NotesGraph" }] }]) {
      const { result } = await ask({}, jsonResponse(body));
      expect(result.ok).toBe(false);
    }
  });

  it("carries the server's error envelope, and says so when the server cannot be reached", async () => {
    const refused = await ask({ page: "x" }, jsonResponse(envelope({ code: "not_found", message: "No such page.", retryable: false }), 404));
    expect(refused.result.ok).toBe(false);
    if (!refused.result.ok) expect(refused.result.error.message).toBe("No such page.");
    const down = await fetchNotes({}, { fetchImpl: (async () => { throw new TypeError("offline"); }) as unknown as typeof fetch });
    expect(down.ok).toBe(false);
  });
});


describe("recordLearnerEvent", () => {
  it("posts the page and the signal to /learner/events and says whether the server saved it", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ pageId: "rag", mastery: { score: 0.6667, events: 1 } }));
    expect(await recordLearnerEvent("rag", "know", { fetchImpl: fetchImpl as unknown as typeof fetch, baseUrl: "http://api" })).toBe(true);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api/learner/events");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ pageId: "rag", signal: "know" });
  });

  it("is false for a refusal and for a server that cannot be reached", async () => {
    const refused = vi.fn(async () => jsonResponse(envelope({ code: "not_found" }), 404));
    expect(await recordLearnerEvent("x", "know", { fetchImpl: refused as unknown as typeof fetch })).toBe(false);
    const down = async () => {
      throw new TypeError("offline");
    };
    expect(await recordLearnerEvent("x", "know", { fetchImpl: down as unknown as typeof fetch })).toBe(false);
  });
});


describe("fetchQuiz and answerQuiz", () => {
  it("asks GET /vault/quiz with the page only when one was chosen, and reads the same body as the notes view", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(GOOD));
    const options = { fetchImpl: fetchImpl as unknown as typeof fetch, baseUrl: "http://api" };
    expect(await fetchQuiz({}, options)).toEqual({ ok: true, workspace: GOOD });
    await fetchQuiz({ page: "a b" }, options);
    expect(fetchImpl.mock.calls.map((c) => String((c as unknown[])[0]))).toEqual(["http://api/vault/quiz", "http://api/vault/quiz?page=a+b"]);
    const bad = vi.fn(async () => jsonResponse({ layout: prebuilt }));
    expect((await fetchQuiz({}, { fetchImpl: bad as unknown as typeof fetch })).ok).toBe(false);
  });

  it("posts the item and the choice to /quiz/answer and returns the server's reading of it", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(quizAnswer()));
    const got = await answerQuiz("claim-1~dense_retrieval", "bm25", { fetchImpl: fetchImpl as unknown as typeof fetch, baseUrl: "http://api" });
    expect(got).toEqual(quizAnswer());
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api/quiz/answer");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ itemId: "claim-1~dense_retrieval", chosenId: "bm25" });
  });

  it("is null for a refusal, a body that is not an answer, and a server that cannot be reached", async () => {
    const refused = vi.fn(async () => jsonResponse(envelope({ code: "not_found" }), 404));
    expect(await answerQuiz("x", "y", { fetchImpl: refused as unknown as typeof fetch })).toBeNull();
    const odd = vi.fn(async () => jsonResponse({ correct: true }));
    expect(await answerQuiz("x", "y", { fetchImpl: odd as unknown as typeof fetch })).toBeNull();
    const down = async () => {
      throw new TypeError("offline");
    };
    expect(await answerQuiz("x", "y", { fetchImpl: down as unknown as typeof fetch })).toBeNull();
  });
});


describe("fetchLint", () => {
  const REPORT = {
    pages: 3,
    orphans: [],
    orphansTotal: 0,
    duplicates: [],
    duplicatesTotal: 0,
    tensions: [],
    tensionsTotal: 0,
    hubs: [],
  };

  it("asks GET /vault/lint and returns a well-formed report", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(REPORT));
    const got = await fetchLint({ fetchImpl: fetchImpl as unknown as typeof fetch, baseUrl: "http://api" });
    expect(got).toEqual({ ok: true, report: REPORT });
    expect(String((fetchImpl.mock.calls[0] as unknown[])[0])).toBe("http://api/vault/lint");
  });

  it("is an error for a body that is not a report, a refusal, and a server that cannot be reached", async () => {
    for (const body of [null, "x", {}, { ...REPORT, orphans: "none" }, { ...REPORT, pages: "3" }]) {
      const fetchImpl = vi.fn(async () => jsonResponse(body));
      expect((await fetchLint({ fetchImpl: fetchImpl as unknown as typeof fetch })).ok).toBe(false);
    }
    const refused = vi.fn(async () => jsonResponse(envelope({ code: "internal", message: "Down." }), 500));
    const result = await fetchLint({ fetchImpl: refused as unknown as typeof fetch });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.message).toBe("Down.");
    const down = async () => {
      throw new TypeError("offline");
    };
    expect((await fetchLint({ fetchImpl: down as unknown as typeof fetch })).ok).toBe(false);
  });
});
