import type { WorkspaceResponse } from "@arcana/schema";
import { describe, expect, it, vi } from "vitest";

import { envelope, jsonResponse, layout, sourceList } from "@/test/fixtures";

import { fetchWorkspace } from "./api";

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
