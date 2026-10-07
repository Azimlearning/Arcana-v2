import type { ErrorEnvelope, LayoutSpec, UIBlock } from "@arcana/schema";
import { describe, expect, it, vi } from "vitest";

import { block, envelope, frame, jsonResponse, layout, sseResponse } from "@/test/fixtures";

import { parseFrame, streamApply, streamChat } from "./stream";

const REQUEST = { message: "q", history: [] };

function collect() {
  const calls = { blocks: [] as UIBlock[], layouts: [] as LayoutSpec[], errors: [] as ErrorEnvelope[], done: 0 };
  const handlers = {
    onBlock: (b: UIBlock) => calls.blocks.push(b),
    onLayout: (l: LayoutSpec) => calls.layouts.push(l),
    onError: (e: ErrorEnvelope) => calls.errors.push(e),
    onDone: () => (calls.done += 1),
  };
  return { calls, handlers };
}

const run = (response: Response | (() => Promise<Response>), signal?: AbortSignal) => {
  const { calls, handlers } = collect();
  const fetchImpl = vi.fn(typeof response === "function" ? response : async () => response);
  return streamChat(REQUEST, handlers, { fetchImpl: fetchImpl as unknown as typeof fetch, baseUrl: "http://api", signal }).then(
    () => ({ calls, fetchImpl }),
  );
};

const FULL = frame({ type: "block", block: block("loading") }) + frame({ type: "block", block: block("ready") }) + frame({ type: "done" });

describe("streamChat", () => {
  it("delivers blocks in order, then done, and never an error", async () => {
    const { calls } = await run(sseResponse([FULL]));
    expect(calls.blocks.map((b) => b.meta.status)).toEqual(["loading", "ready"]);
    expect(calls.done).toBe(1);
    expect(calls.errors).toEqual([]);
  });

  it("delivers a readable layout after the blocks and before done", async () => {
    const placed = layout([{ blockId: "turn-1", panel: "chat", region: "main" as const, order: 0 }]);
    const { calls } = await run(sseResponse([FULL.replace(frame({ type: "done" }), frame({ type: "layout", layout: placed }) + frame({ type: "done" }))]));
    expect(calls.layouts).toEqual([placed]);
    expect(calls.done).toBe(1);
    expect(calls.errors).toEqual([]);
  });

  it("reads a version 1 layout (no regions) as one main region in every panel", async () => {
    const v1 = {
      version: 1,
      origin: "adaptive",
      mode: "research",
      panels: [{ id: "sources", width: 20 }, { id: "chat", width: 45 }, { id: "studio", width: 35 }],
      placements: [{ blockId: "turn-1", panel: "chat", order: 0 }],
    };
    const { calls } = await run(sseResponse([FULL.replace(frame({ type: "done" }), frame({ type: "layout", layout: v1 as never }) + frame({ type: "done" }))]));
    expect(calls.layouts).toEqual([layout([{ blockId: "turn-1", panel: "chat", region: "main" as const, order: 0 }])]);
  });

  it("ignores a layout it cannot read, without an error and without losing the rest of the turn", async () => {
    const unknownVersion = layout([], { version: 3 });
    const { calls } = await run(sseResponse([FULL.replace(frame({ type: "done" }), frame({ type: "layout", layout: unknownVersion }) + frame({ type: "done" }))]));
    expect(calls.layouts).toEqual([]);
    expect(calls.blocks).toHaveLength(2);
    expect(calls.done).toBe(1);
    expect(calls.errors).toEqual([]);
  });

  it("a stream from a server that sends no layout still works (the handler is optional)", async () => {
    const fetchImpl = vi.fn(async () => sseResponse([FULL]));
    let done = 0;
    await streamChat(REQUEST, { onBlock: () => {}, onError: () => {}, onDone: () => (done += 1) }, { fetchImpl: fetchImpl as unknown as typeof fetch, baseUrl: "http://api" });
    expect(done).toBe(1);
  });

  it("posts the request as JSON to /chat", async () => {
    const { fetchImpl } = await run(sseResponse([FULL]));
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(REQUEST);
  });

  it("reassembles frames split at every possible boundary", async () => {
    for (const size of [1, 2, 7, 33, 200]) {
      const chunks = FULL.match(new RegExp(`[\\s\\S]{1,${size}}`, "g")) ?? [];
      const { calls } = await run(sseResponse(chunks));
      expect(calls.blocks).toHaveLength(2);
      expect(calls.done).toBe(1);
      expect(calls.errors).toEqual([]);
    }
  });

  it("handles CRLF line endings, comments and keep-alives", async () => {
    const crlf = FULL.replace(/\n/g, "\r\n");
    const { calls } = await run(sseResponse([": keep-alive\r\n\r\n", crlf]));
    expect(calls.blocks).toHaveLength(2);
    expect(calls.done).toBe(1);
  });

  it("makes an error event the single terminal and ignores a following done", async () => {
    const stream = frame({ type: "block", block: block("loading") }) + frame({ type: "error", error: envelope({ message: "boom" }) }) + frame({ type: "done" });
    const { calls } = await run(sseResponse([stream]));
    expect(calls.errors.map((e) => e.message)).toEqual(["boom"]);
    expect(calls.done).toBe(0);
  });

  it("reports an error when the stream closes without done", async () => {
    const { calls } = await run(sseResponse([frame({ type: "block", block: block("loading") })]));
    expect(calls.blocks).toHaveLength(1);
    expect(calls.done).toBe(0);
    expect(calls.errors).toHaveLength(1);
    expect(calls.errors[0]?.message).toMatch(/closed before the answer was complete/);
  });

  it("reports a lost connection when the stream breaks mid-way, keeping what arrived", async () => {
    const { calls } = await run(sseResponse([frame({ type: "block", block: block("loading") })], { breakAfter: true }));
    expect(calls.blocks.map((b) => b.meta.status)).toEqual(["loading"]);
    expect(calls.errors).toHaveLength(1);
    expect(calls.errors[0]).toMatchObject({ code: "provider_unavailable", retryable: true });
    expect(calls.done).toBe(0);
  });

  it("passes a server error envelope through unchanged", async () => {
    const sent = envelope({ code: "validation_failed", message: "bad", retryable: false, issues: [{ path: "message", message: "required" }] });
    const { calls } = await run(jsonResponse(sent, 422));
    expect(calls.errors).toEqual([sent]);
    expect(calls.blocks).toEqual([]);
  });

  it("builds a generic retryable error for a non-JSON 5xx", async () => {
    const { calls } = await run(new Response("<html>Bad gateway</html>", { status: 502 }));
    expect(calls.errors[0]).toMatchObject({ code: "provider_unavailable", retryable: true });
    expect(calls.errors[0]?.message).toContain("502");
  });

  it("reports an unreachable server", async () => {
    const { calls } = await run(() => Promise.reject(new TypeError("fetch failed")));
    expect(calls.errors[0]?.message).toBe("Could not reach the server.");
  });

  it("treats a malformed frame as a terminal, non-retryable error and ignores what follows", async () => {
    const { calls } = await run(sseResponse(["data: {not json\n\n", FULL]));
    expect(calls.errors).toHaveLength(1);
    expect(calls.errors[0]?.retryable).toBe(false);
    expect(calls.blocks).toEqual([]);
    expect(calls.done).toBe(0);
  });

  it("rejects an event it does not recognise instead of passing it on", async () => {
    const { calls } = await run(sseResponse([`data: ${JSON.stringify({ type: "mystery" })}\n\n`]));
    expect(calls.errors).toHaveLength(1);
  });

  it("is silent when the caller aborts", async () => {
    const controller = new AbortController();
    controller.abort();
    const { calls } = await run(() => Promise.reject(new DOMException("aborted", "AbortError")), controller.signal);
    expect(calls).toEqual({ blocks: [], layouts: [], errors: [], done: 0 });
  });
});

describe("parseFrame", () => {
  it("returns null for a frame with no data lines", () => {
    expect(parseFrame(": comment")).toBeNull();
    expect(parseFrame("event: ping")).toBeNull();
  });

  it("joins multiple data lines before parsing", () => {
    expect(parseFrame('data: {"type":\ndata: "done"}')).toEqual({ type: "done" });
  });

  it("throws on a block with no type discriminator", () => {
    expect(() => parseFrame(`data: ${JSON.stringify({ type: "block", block: {} })}`)).toThrow();
  });
});

describe("streamApply", () => {
  it("posts to the pattern's apply endpoint (encoded), with no body, and delivers blocks, layout and done", async () => {
    const placed = layout([{ blockId: "turn-1", panel: "chat", region: "main" as const, order: 0 }]);
    const body = frame({ type: "block", block: block("ready") }) + frame({ type: "layout", layout: placed }) + frame({ type: "done" });
    const { calls, handlers } = collect();
    const fetchImpl = vi.fn(async () => sseResponse([body]));
    await streamApply("a/b", handlers, { fetchImpl: fetchImpl as unknown as typeof fetch, baseUrl: "http://api" });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api/patterns/a%2Fb/apply");
    expect(init.method).toBe("POST");
    expect(init.body).toBeUndefined();
    expect(calls.blocks).toHaveLength(1);
    expect(calls.layouts).toEqual([placed]);
    expect(calls.done).toBe(1);
  });

  it("delivers a refusal as an error and no block", async () => {
    const refusal = envelope({ code: "pattern_refused", message: "This saved view cannot be shown.", retryable: false, issues: [{ path: "template_changed", message: "m" }] });
    const { calls, handlers } = collect();
    const fetchImpl = vi.fn(async () => jsonResponse(refusal, 409));
    await streamApply("p-1", handlers, { fetchImpl: fetchImpl as unknown as typeof fetch, baseUrl: "http://api" });
    expect(calls.errors).toEqual([refusal]);
    expect(calls.blocks).toEqual([]);
    expect(calls.done).toBe(0);
  });
});

