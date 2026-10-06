import { beforeEach, describe, expect, it } from "vitest";

import { block, comparisonGrid, conceptMap, envelope, graphView, sourceList } from "@/test/fixtures";

import { toErrorBlock, useWorkspace } from "./store";

beforeEach(() => useWorkspace.setState(useWorkspace.getInitialState(), true));

const s = () => useWorkspace.getState();

describe("workspace store", () => {
  it("replaces a block with the same id in place, keeping its position", () => {
    s().startTurn();
    s().upsertBlock(block("loading"));
    s().upsertBlock({ ...block("loading"), id: "other" });
    s().upsertBlock(block("ready")); // same id as the first: replaces it

    expect(s().order).toEqual(["turn-1", "other"]);
    expect(s().blocks["turn-1"]?.meta.status).toBe("ready");
    expect(Object.keys(s().blocks)).toHaveLength(2);
  });

  it("starts a turn with an empty panel but keeps the documents", () => {
    s().addDocument({ docId: "d", title: "T", status: "ready", chunkCount: 4, error: null });
    s().upsertBlock(block("ready"));
    s().startTurn();
    expect(s().order).toEqual([]);
    expect(s().blocks).toEqual({});
    expect(s().turn).toBe("streaming");
    expect(s().documents).toHaveLength(1);
  });

  it("turns a block that is still loading or partial into an error block when the turn fails", () => {
    const reason = envelope({ message: "connection lost" });
    s().startTurn();
    s().upsertBlock(block("loading"));
    s().upsertBlock({ ...block("partial"), id: "p" });
    s().upsertBlock({ ...block("ready"), id: "r" });
    s().upsertBlock({ ...block("empty"), id: "e" });
    s().failTurn(reason);

    expect(s().blocks["turn-1"]?.meta).toMatchObject({ status: "error", error: reason });
    expect(s().blocks["p"]?.meta.status).toBe("error");
    expect(s().blocks["p"]?.data).toEqual({ segments: [], citations: [] }); // no half-shown content
    expect(s().blocks["r"]?.meta.status).toBe("ready"); // finished blocks are left alone
    expect(s().blocks["e"]?.meta.status).toBe("empty");
    expect(s().turn).toBe("failed");
    expect(s().turnError).toEqual(reason);
  });

  it("finishes only a streaming turn, never overwriting a failure", () => {
    s().startTurn();
    s().finishTurn();
    expect(s().turn).toBe("idle");
    s().startTurn();
    s().failTurn(envelope());
    s().finishTurn();
    expect(s().turn).toBe("failed");
  });

  it("keeps one entry per document id", () => {
    s().addDocument({ docId: "d", title: "First", status: "ready", chunkCount: 1, error: null });
    s().addDocument({ docId: "d", title: "Again", status: "ready", chunkCount: 2, error: null });
    expect(s().documents).toEqual([{ docId: "d", title: "Again", status: "ready", chunkCount: 2, error: null }]);
  });

  it("toErrorBlock keeps identity and panel, clears content", () => {
    const failed = toErrorBlock(block("ready"), envelope());
    expect(failed.id).toBe("turn-1");
    expect(failed.meta).toMatchObject({ panel: "chat", status: "error" });
    expect(failed.data).toEqual({ segments: [], citations: [] });
  });

  it("toErrorBlock empties a ConceptMap too, and keeps its own panel", () => {
    const failed = toErrorBlock(conceptMap("ready"), envelope());
    expect(failed.meta).toMatchObject({ panel: "studio", status: "error" });
    expect(failed.data).toEqual({ steps: [], citations: [] });
  });

  it("toErrorBlock empties a ComparisonGrid too, and keeps its own panel", () => {
    const failed = toErrorBlock(comparisonGrid("ready"), envelope());
    expect(failed.meta).toMatchObject({ panel: "chat", status: "error" });
    expect(failed.data).toEqual({ dimensions: [], rows: [], citations: [] });
  });

  it("toErrorBlock empties a GraphView too, and keeps its own panel", () => {
    const failed = toErrorBlock(graphView("ready"), envelope());
    expect(failed.meta).toMatchObject({ panel: "studio", status: "error" });
    expect(failed.data).toEqual({ nodes: [], edges: [], citations: [] });
  });

  it("toErrorBlock empties a SourceList too, and keeps its own panel", () => {
    const failed = toErrorBlock(sourceList("partial"), envelope());
    expect(failed.type).toBe("SourceList");
    expect(failed.meta).toMatchObject({ panel: "sources", status: "error" });
    expect(failed.data).toEqual({ documents: [] });
  });
});
