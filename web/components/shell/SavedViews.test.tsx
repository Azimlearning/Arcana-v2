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
  const open = () => fireEvent.click(screen.getByText(/Saved views \(/));

  it("says there are none yet, with how to save one", () => {
    render(<SavedViews patterns={[]} busy={false} message={null} onApply={vi.fn()} onDelete={vi.fn()} />);
    open();
    expect(screen.getByText(/No saved views yet/)).toBeInTheDocument();
    expect(screen.getByText("Saved views (0)")).toBeInTheDocument();
  });

  it("shows a view and deletes one by its own button, naming the view", () => {
    const onApply = vi.fn();
    const onDelete = vi.fn();
    render(<SavedViews patterns={[savedPattern(), savedPattern({ id: "p-2", name: "Other" })]} busy={false} message={null} onApply={onApply} onDelete={onDelete} />);
    open();
    fireEvent.click(screen.getByRole("button", { name: "Show Other" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete Dense vs BM25" }));
    expect(onApply).toHaveBeenCalledWith("p-2");
    expect(onDelete).toHaveBeenCalledWith("p-1");
  });

  it("cannot start a second view while one is being shown", () => {
    render(<SavedViews patterns={[savedPattern()]} busy message={null} onApply={vi.fn()} onDelete={vi.fn()} />);
    open();
    expect(screen.getByRole("button", { name: "Show Dense vs BM25" })).toBeDisabled();
  });

  it("announces a message as an alert and renders names as text, never markup", () => {
    const hostile = "<img src=x onerror=alert(1)>";
    const { container } = render(
      <SavedViews patterns={[savedPattern({ name: hostile })]} busy={false} message="Your documents no longer support this view." onApply={vi.fn()} onDelete={vi.fn()} />,
    );
    open();
    expect(screen.getByRole("alert")).toHaveTextContent("Your documents no longer support this view.");
    expect(container.querySelector("img")).toBeNull();
    expect(within(screen.getByRole("list", { name: "Saved views" })).getByText(hostile)).toBeInTheDocument();
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
