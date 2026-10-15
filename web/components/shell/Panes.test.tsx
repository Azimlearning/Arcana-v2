import type { UIBlock } from "@arcana/schema";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { block, graphView, learningInsights, studyPlan } from "@/test/fixtures";

import { MAX_SHARE, MIN_SHARE, PaneSeparator, Panes } from "./Panes";

const setup = (panes: UIBlock[] = [studyPlan("ready"), graphView("ready")]) => {
  const onClose = vi.fn();
  const onCloseAll = vi.fn();
  const onToggleFocus = vi.fn();
  render(<Panes panes={panes} onClose={onClose} onCloseAll={onCloseAll} focused={false} onToggleFocus={onToggleFocus} />);
  return { onClose, onCloseAll, onToggleFocus };
};

afterEach(() => vi.unstubAllGlobals());

describe("Panes", () => {
  it("shows each block in its own labelled pane, through the registry, and says how many are open", () => {
    setup();
    expect(screen.getByRole("status")).toHaveTextContent("2 panes open");
    const plan = within(screen.getByRole("region", { name: "Pane: Review schedule" }));
    expect(plan.getByRole("region", { name: "Review schedule" })).toBeInTheDocument(); // the block itself
    expect(screen.getByRole("region", { name: "Pane: Connection graph" })).toBeInTheDocument();
  });

  it("closes one pane, or all of them, or expands", () => {
    const { onClose, onCloseAll, onToggleFocus } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Close pane: Review schedule" }));
    expect(onClose).toHaveBeenCalledWith("turn-1-study-plan");
    fireEvent.click(screen.getByRole("button", { name: "Close all" }));
    expect(onCloseAll).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Expand" }));
    expect(onToggleFocus).toHaveBeenCalled();
  });

  it("a block with tabular facts has a Table view, sortable and filterable, and one without has none", () => {
    setup();
    const plan = within(screen.getByRole("region", { name: "Pane: Review schedule" }));
    fireEvent.click(plan.getByRole("button", { name: "Table" }));
    const table = plan.getByRole("table");
    const names = () => within(table).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0]!.textContent);
    expect(names()).toEqual(["BM25", "reciprocal rank fusion", "dense retrieval"]);
    fireEvent.click(within(table).getByRole("button", { name: "Mastery %" }));
    expect(names()).toEqual(["BM25", "reciprocal rank fusion", "dense retrieval"]); // 20, 60, 90 ascending
    fireEvent.click(within(table).getByRole("button", { name: /Mastery %/ }));
    expect(names()).toEqual(["dense retrieval", "reciprocal rank fusion", "BM25"]); // descending
    expect(within(table).getByRole("columnheader", { name: /Mastery %/ })).toHaveAttribute("aria-sort", "descending");
    fireEvent.change(plan.getByLabelText("Filter Review schedule"), { target: { value: "fusion" } });
    expect(names()).toEqual(["reciprocal rank fusion"]);
    expect(plan.getByRole("status")).toHaveTextContent("1 of 3 rows");
    const graph = within(screen.getByRole("region", { name: "Pane: Connection graph" }));
    expect(graph.queryByRole("group", { name: "View" })).not.toBeInTheDocument();
  });

  it("a block with several tables shows each, and the CSV download is the table as shown", () => {
    const created: Blob[] = [];
    vi.stubGlobal("URL", { ...URL, createObjectURL: (b: Blob) => (created.push(b), "blob:x"), revokeObjectURL: () => {} });
    setup([learningInsights("ready")]);
    fireEvent.click(screen.getByRole("button", { name: "Table" }));
    expect(screen.getAllByRole("table")).toHaveLength(3);
    fireEvent.click(within(screen.getByRole("region", { name: "Weakest pages" })).getByRole("button", { name: "Download CSV" }));
    expect(created).toHaveLength(1);
    expect(created[0]!.type).toBe("text/csv;charset=utf-8");
  });

  it("an answer opens as its sources table", () => {
    setup([block("ready")]);
    fireEvent.click(screen.getByRole("button", { name: "Table" }));
    expect(screen.getByRole("region", { name: "Sources" })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3); // the header and two citations
  });
});

describe("PaneSeparator", () => {
  it("is a keyboard-operable separator whose value is the panes' share, kept within its limits", () => {
    const onShare = vi.fn();
    const container = { current: document.createElement("div") };
    render(<PaneSeparator share={45} onShare={onShare} container={container} />);
    const sep = screen.getByRole("separator", { name: "Resize the panes" });
    expect(sep).toHaveAttribute("aria-valuenow", "45");
    expect(sep).toHaveAttribute("aria-valuemin", String(MIN_SHARE));
    expect(sep).toHaveAttribute("aria-valuemax", String(MAX_SHARE));
    fireEvent.keyDown(sep, { key: "ArrowLeft" });
    expect(onShare).toHaveBeenLastCalledWith(50); // moving the divider left gives the panes more room
    fireEvent.keyDown(sep, { key: "ArrowRight" });
    expect(onShare).toHaveBeenLastCalledWith(40);
  });

  it("never asks for a share outside its limits", () => {
    const onShare = vi.fn();
    const container = { current: document.createElement("div") };
    const { rerender } = render(<PaneSeparator share={68} onShare={onShare} container={container} />);
    fireEvent.keyDown(screen.getByRole("separator"), { key: "ArrowLeft" });
    expect(onShare).toHaveBeenLastCalledWith(MAX_SHARE);
    rerender(<PaneSeparator share={32} onShare={onShare} container={container} />);
    fireEvent.keyDown(screen.getByRole("separator"), { key: "ArrowRight" });
    expect(onShare).toHaveBeenLastCalledWith(MIN_SHARE);
  });
});
