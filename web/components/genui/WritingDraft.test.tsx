import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TITLE, envelope, writingDraft } from "@/test/fixtures";

import { WritingDraft, bibliographyText, draftMarkdown } from "./WritingDraft";

describe("WritingDraft: the five wire states", () => {
  it("loading: a busy status and none of the draft", () => {
    render(<WritingDraft block={writingDraft("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText(/Dense retrieval embeds/)).not.toBeInTheDocument();
  });

  it("empty: says nothing could be drafted, and is not announced as a failure", () => {
    render(<WritingDraft block={writingDraft("empty")} />);
    expect(screen.getByText("Nothing could be drafted from your documents.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert", () => {
    render(<WritingDraft block={writingDraft("error", {}, envelope({ message: "The draft failed validation.", retryable: true }))} />);
    expect(within(screen.getByRole("alert")).getByText("The draft failed validation.")).toBeInTheDocument();
  });

  it("error without a reason still renders a message, never a blank panel", () => {
    render(<WritingDraft block={writingDraft("error")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("could not be produced");
  });

  it("partial: shows what has arrived and says it is not final", () => {
    render(<WritingDraft block={writingDraft("partial")} />);
    expect(screen.getByText(/BM25 scores exact terms/)).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });

  it("ready: title, headed sections in order with citation pills, then sources and references", () => {
    render(<WritingDraft block={writingDraft("ready")} />);
    expect(screen.getByRole("heading", { name: "Hybrid retrieval in brief" })).toBeInTheDocument();
    const draft = screen.getByRole("region", { name: "Draft" });
    const first = within(draft).getByText(/Dense retrieval embeds passages/);
    const second = within(draft).getByText(/BM25 scores exact terms/);
    expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(draft).getByRole("heading", { name: "Sparse methods" })).toBeInTheDocument();
    expect(within(draft).getAllByRole("link", { name: /^Source c1/ })).toHaveLength(2);
    expect(screen.getByRole("region", { name: "Sources" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Bibliography" })).toBeInTheDocument();
    expect(screen.queryByText(/not final/i)).not.toBeInTheDocument();
  });
});

describe("WritingDraft: references", () => {
  it("shows the references exactly as sent, in the chosen style", () => {
    render(<WritingDraft block={writingDraft("ready")} />);
    const bib = screen.getByRole("region", { name: "Bibliography" });
    expect(within(bib).getByText(`${TITLE}.`)).toBeInTheDocument();
    expect(within(bib).getByText("BM25 in Practice. arXiv:2401.00001.")).toBeInTheDocument();
    fireEvent.click(within(bib).getByRole("button", { name: "IEEE" }));
    expect(within(bib).getByText('"BM25 in Practice," arXiv:2401.00001.')).toBeInTheDocument();
    fireEvent.click(within(bib).getByRole("button", { name: "BibTeX" }));
    expect(within(bib).getByText(/@misc\{arcanae/)).toBeInTheDocument();
  });

  it("offers copy and downloads, and the helpers return what was sent without adding to it", () => {
    const { data } = writingDraft("ready");
    render(<WritingDraft block={writingDraft("ready")} />);
    expect(screen.getByRole("button", { name: "Copy references" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download .bib" })).toBeInTheDocument();
    expect(bibliographyText(data.bibliography, "apa")).toBe(`${TITLE}.\nBM25 in Practice. arXiv:2401.00001.`);
    const md = draftMarkdown(data, "apa");
    expect(md).toContain("# Hybrid retrieval in brief");
    expect(md).toContain("BM25 scores exact terms. [c1][c2]");
    expect(md).toContain("## References");
  });

  it("a citation id with no matching citation renders no pill (never a dead link)", () => {
    const block = writingDraft("ready");
    block.data.sections[0]!.segments[0]!.citationIds = ["c9"];
    render(<WritingDraft block={block} />);
    expect(screen.queryByRole("link", { name: /Source c9/ })).not.toBeInTheDocument();
  });
});

describe("WritingDraft: kinds and the audio-overview script (D-43)", () => {
  const script = () =>
    writingDraft("ready", {
      kind: "script",
      title: "An overview of hybrid retrieval",
      sections: [
        {
          heading: "Opening",
          segments: [
            { speaker: "host", text: "What does dense retrieval do?", citationIds: ["c1"] },
            { speaker: "guest", text: "It embeds passages and queries.", citationIds: ["c1"] },
          ],
        },
      ],
    });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("names the kind above the title, and an outline by default", () => {
    const { unmount } = render(<WritingDraft block={writingDraft("ready")} />);
    expect(screen.getByText("Outline")).toBeInTheDocument();
    unmount();
    render(<WritingDraft block={writingDraft("ready", { kind: "literature_review" })} />);
    expect(screen.getByText("Literature review")).toBeInTheDocument();
  });

  it("shows a script as turns, each with its speaker in words, and the citation pills", () => {
    render(<WritingDraft block={script()} />);
    expect(screen.getByText("Audio overview")).toBeInTheDocument();
    expect(screen.getByText("Host:")).toBeInTheDocument();
    expect(screen.getByText("Guest:")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Source c1/ }).length).toBeGreaterThan(0);
  });

  it("reads the lines aloud in order with the browser's voice, and stops", () => {
    const spoken: string[] = [];
    const cancel = vi.fn();
    vi.stubGlobal("speechSynthesis", { speak: (u: { text: string }) => spoken.push(u.text), cancel });
    vi.stubGlobal(
      "SpeechSynthesisUtterance",
      class {
        pitch = 1;
        onend: (() => void) | null = null;
        constructor(public text: string) {}
      },
    );
    render(<WritingDraft block={script()} />);
    fireEvent.click(screen.getByRole("button", { name: "Listen" }));
    expect(spoken).toEqual(["What does dense retrieval do?", "It embeds passages and queries."]);
    expect(screen.getByRole("status")).toHaveTextContent("Reading aloud");
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(cancel).toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Nothing is sent anywhere");
  });

  it("says so, and draws no Listen button, when the browser cannot speak", () => {
    render(<WritingDraft block={script()} />);
    expect(screen.queryByRole("button", { name: "Listen" })).not.toBeInTheDocument();
    expect(screen.getByText(/cannot read aloud/)).toBeInTheDocument();
  });

  it("an outline has no read-aloud control", () => {
    render(<WritingDraft block={writingDraft("ready")} />);
    expect(screen.queryByRole("group", { name: "Read aloud" })).not.toBeInTheDocument();
  });

  it("the Markdown of a script keeps who said each line", () => {
    const md = draftMarkdown(script().data, "apa");
    expect(md).toContain("**Host:** What does dense retrieval do?");
    expect(md).toContain("**Guest:** It embeds passages and queries.");
  });
});
