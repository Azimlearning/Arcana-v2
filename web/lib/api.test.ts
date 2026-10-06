import type { WorkspaceResponse } from "@arcana/schema";
import { describe, expect, it, vi } from "vitest";

import { envelope, jsonResponse, layout, savedPattern, sourceList } from "@/test/fixtures";

import { deletePattern, fetchWorkspace, isSavedPattern, listPatterns, reverifyPattern, savePattern } from "./api";

const prebuilt = layout([{ blockId: "workspace-sources", panel: "sources", order: 0 }], {
  origin: "prebuilt",
  mode: "basic",
  panels: [
    { id: "sources", width: 20 },
    { id: "chat", width: 60 },
    { id: "studio", width: 20 },
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
      { layout: { ...prebuilt, version: 2 }, blocks: GOOD.blocks }, // a layout this client cannot read
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
