import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { envelope, savedPattern } from "@/test/fixtures";

import { SaveView } from "./SaveView";
import { SavedViews, refusalWords } from "./SavedViews";

describe("refusalWords", () => {
  const refusal = (reason: string) => envelope({ code: "pattern_refused", message: "This saved view cannot be shown.", issues: [{ path: reason, message: "m" }] });

  it("says each refusal reason in plain words", () => {
    expect(refusalWords(refusal("precondition_not_met"))).toBe("Your documents no longer support this view.");
    expect(refusalWords(refusal("document_missing"))).toBe("A document this view needs is no longer in your library.");
    expect(refusalWords(refusal("template_changed"))).toMatch(/older version.*checked again/);
  });

  it("uses a generic sentence for a reason it does not know, and the server's message for any other error", () => {
    expect(refusalWords(refusal("something_new"))).toBe("This saved view cannot be shown.");
    expect(refusalWords(envelope({ code: "pattern_refused", message: "x", issues: [] }))).toBe("This saved view cannot be shown.");
    expect(refusalWords(envelope({ code: "not_found", message: "No saved view has that id." }))).toBe("No saved view has that id.");
  });
});

describe("SavedViews", () => {
  it("says there are none yet, with how to save one", () => {
    render(<SavedViews patterns={[]} busy={false} message={null} onApply={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText(/Nothing here yet/)).toBeInTheDocument();
    expect(screen.getByText("Saved views (0)")).toBeInTheDocument();
  });

  it("shows a view and deletes one by its own button, naming the view", () => {
    const onApply = vi.fn();
    const onDelete = vi.fn();
    render(<SavedViews patterns={[savedPattern(), savedPattern({ id: "p-2", name: "Other" })]} busy={false} message={null} onApply={onApply} onDelete={onDelete} />);
    fireEvent.click(screen.getByRole("button", { name: "Show Other" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete Dense vs BM25" }));
    expect(onApply).toHaveBeenCalledWith("p-2");
    expect(onDelete).toHaveBeenCalledWith("p-1");
  });

  it("cannot start a second view while one is being shown", () => {
    render(<SavedViews patterns={[savedPattern()]} busy message={null} onApply={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Show Dense vs BM25" })).toBeDisabled();
  });

  it("announces a message as an alert and renders names as text, never markup", () => {
    const hostile = "<img src=x onerror=alert(1)>";
    const { container } = render(
      <SavedViews patterns={[savedPattern({ name: hostile })]} busy={false} message="Your documents no longer support this view." onApply={vi.fn()} onDelete={vi.fn()} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Your documents no longer support this view.");
    expect(container.querySelector("img")).toBeNull();
    expect(within(screen.getByRole("list", { name: "Saved views" })).getByText(hostile)).toBeInTheDocument();
  });
});

describe("SavedViews: where each view is in its life", () => {
  const render1 = (patterns: ReturnType<typeof savedPattern>[], staleId: string | null = null) =>
    render(<SavedViews patterns={patterns} busy={false} message={null} staleId={staleId} onApply={vi.fn()} onDelete={vi.fn()} />);

  it("says the kind, the state in words and how often it was shown", () => {
    render1([
      savedPattern({ id: "a", name: "A", state: "saved", useCount: 0 }),
      savedPattern({ id: "b", name: "B", state: "verified", useCount: 1 }),
      savedPattern({ id: "c", name: "C", state: "generated", useCount: 3 }),
    ]);
    const items = within(screen.getByRole("list", { name: "Saved views" })).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Connection graph · Saved · not shown yet");
    expect(items[1]).toHaveTextContent("Connection graph · Checked again · shown once");
    expect(items[2]).toHaveTextContent("Connection graph · Made, not yet checked · shown 3 times");
  });

  it("says Needs checking for the view whose layout moved on", () => {
    render1([savedPattern({ id: "a", name: "A" }), savedPattern({ id: "b", name: "B" })], "b");
    const items = within(screen.getByRole("list", { name: "Saved views" })).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Saved");
    expect(items[1]).toHaveTextContent("Needs checking");
  });

  it("is a labelled section for the outputs shelf, always shown (nothing to open)", () => {
    render1([]);
    expect(screen.getByRole("region", { name: "Saved views section" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Saved views (0)" })).toBeInTheDocument();
  });
});

describe("SavedViews: checking a stale view again", () => {
  it("offers Check this view again only for the view whose layout moved on, and reports it", () => {
    const onReverify = vi.fn();
    const { rerender } = render(<SavedViews patterns={[savedPattern()]} busy={false} message="needs checking" onApply={vi.fn()} onDelete={vi.fn()} onReverify={onReverify} />);
    expect(screen.queryByRole("button", { name: "Check this view again" })).not.toBeInTheDocument();
    rerender(<SavedViews patterns={[savedPattern()]} busy={false} message="needs checking" staleId="p-1" onApply={vi.fn()} onDelete={vi.fn()} onReverify={onReverify} />);
    fireEvent.click(screen.getByRole("button", { name: "Check this view again" }));
    expect(onReverify).toHaveBeenCalledWith("p-1");
  });
});

describe("SaveView", () => {
  it("collects a name and reports it, then confirms", async () => {
    const onSave = vi.fn(async () => ({ ok: true as const }));
    render(<SaveView defaultName="Connection graph" onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Save this view" }));
    expect(screen.getByLabelText("Name")).toHaveValue("Connection graph");
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Mine" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved.");
    expect(onSave).toHaveBeenCalledWith("Mine");
  });

  it("will not save a blank name, can be cancelled, and shows a refusal", async () => {
    const onSave = vi.fn(async () => ({ ok: false as const, message: "A saved view needs a name." }));
    render(<SaveView defaultName="x" onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Save this view" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "ok" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A saved view needs a name.");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Save this view" })).toBeInTheDocument();
  });
});
