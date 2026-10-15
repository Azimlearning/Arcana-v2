import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TITLE, docBrief, envelope } from "@/test/fixtures";

import { DocBrief, briefMarkdown } from "./DocBrief";
import { NotesNav } from "./notesNav";

describe("DocBrief: the wire states", () => {
  it("loading: a busy status and none of the brief", () => {
    render(<DocBrief block={docBrief("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("region", { name: "Key points" })).not.toBeInTheDocument();
  });

  it("empty: says why in words, and is not announced as a failure", () => {
    render(<DocBrief block={docBrief("empty")} />);
    expect(screen.getByText("No brief could be made.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert", () => {
    render(<DocBrief block={docBrief("error", {}, envelope({ message: "The vault is unreadable." }))} />);
    expect(within(screen.getByRole("alert")).getByText("The vault is unreadable.")).toBeInTheDocument();
  });

  it("partial: shows what is there and says it is not final", () => {
    render(<DocBrief block={docBrief("partial")} />);
    expect(screen.getByRole("region", { name: "Key points" })).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });
});

describe("DocBrief: ready", () => {
  it("shows the title, the key points with their source and the concepts they name, the terms and the next steps", () => {
    render(<DocBrief block={docBrief("ready")} />);
    expect(screen.getByRole("heading", { name: TITLE })).toBeInTheDocument();
    const points = within(screen.getByRole("region", { name: "Key points" }));
    expect(points.getByText("Dense retrieval embeds passages and BM25 scores exact terms.")).toBeInTheDocument();
    expect(points.getByText("Names: dense retrieval, BM25")).toBeInTheDocument();
    expect(points.getAllByText(new RegExp(TITLE)).length).toBeGreaterThan(0);
    const terms = within(screen.getByRole("region", { name: "Key terms" }));
    expect(terms.getByText("Dense retrieval is a method that embeds text into vectors.")).toBeInTheDocument();
    const steps = within(screen.getByRole("region", { name: "Next steps" }));
    expect(steps.getByText("Your mastery is 20 percent: revisit it.")).toBeInTheDocument();
    expect(steps.getByText("Review")).toBeInTheDocument();
    expect(steps.getByText("Quiz")).toBeInTheDocument();
  });

  it("says how much of the vault it used and that it is not a summary", () => {
    render(<DocBrief block={docBrief("ready")} />);
    expect(screen.getByText(/Made from the 9 claims/)).toBeInTheDocument();
    expect(screen.getByText(/3 more are not shown/)).toBeInTheDocument();
    expect(screen.getByText(/not a\s+summary/)).toBeInTheDocument();
  });

  it("a page name opens the page when the notes screen can, and is plain text when it cannot", () => {
    const openPage = vi.fn();
    const { unmount } = render(
      <NotesNav.Provider value={{ openPage }}>
        <DocBrief block={docBrief("ready")} />
      </NotesNav.Provider>,
    );
    fireEvent.click(within(screen.getByRole("region", { name: "Key terms" })).getByRole("button", { name: "dense retrieval" }));
    expect(openPage).toHaveBeenCalledWith("dense_retrieval");
    unmount();
    render(<DocBrief block={docBrief("ready")} />);
    expect(within(screen.getByRole("region", { name: "Key terms" })).queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders the document's text as text, never as markup", () => {
    const quote = 'A <img src=x onerror="alert(1)"> **claim** in the document.';
    const brief = docBrief("ready");
    brief.data.citations[0]!.quote = quote;
    const { container } = render(<DocBrief block={brief} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container).toHaveTextContent('<img src=x onerror="alert(1)">');
  });

  it("a point whose citation is missing renders nothing (never a dead entry)", () => {
    const brief = docBrief("ready");
    brief.data.keyPoints[0]!.citationId = "gone";
    render(<DocBrief block={brief} />);
    expect(within(screen.getByRole("region", { name: "Key points" })).getAllByRole("listitem")).toHaveLength(1);
  });

  it("the Markdown holds exactly the block's own text", () => {
    const md = briefMarkdown(docBrief("ready").data);
    expect(md).toContain(`# Brief: ${TITLE}`);
    expect(md).toContain("- Reciprocal rank fusion merges two ranked lists.");
    expect(md).toContain("- **dense retrieval**: Dense retrieval is a method that embeds text into vectors.");
    expect(md).toContain("- Review BM25: Your mastery is 20 percent: revisit it.");
  });
});
