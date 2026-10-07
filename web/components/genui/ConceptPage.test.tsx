import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TITLE, conceptPage, envelope } from "@/test/fixtures";

import { ConceptPage } from "./ConceptPage";
import { NotesNav } from "./notesNav";

describe("ConceptPage: the wire states", () => {
  it("loading: a busy status and no page", () => {
    render(<ConceptPage block={conceptPage("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("empty: says there is no page to show, not announced as a failure", () => {
    render(<ConceptPage block={conceptPage("empty")} />);
    expect(screen.getByText("No page to show.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert", () => {
    render(<ConceptPage block={conceptPage("error", {}, envelope({ message: "The vault is unreadable." }))} />);
    expect(within(screen.getByRole("alert")).getByText("The vault is unreadable.")).toBeInTheDocument();
  });

  it("partial: shows what is there and says it is not final", () => {
    render(<ConceptPage block={conceptPage("partial")} />);
    expect(screen.getByRole("article", { name: "Retrieval-Augmented Generation" })).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });
});

describe("ConceptPage: ready", () => {
  it("names the concept, its other spellings and how widely it occurs", () => {
    render(<ConceptPage block={conceptPage("ready")} />);
    expect(screen.getByRole("heading", { name: "Retrieval-Augmented Generation" })).toBeInTheDocument();
    expect(screen.getByText(/Mentioned in 2 passages across 2 documents/)).toBeInTheDocument();
    expect(screen.getByText("Also written: RAG.")).toBeInTheDocument();
  });

  it("shows each definition as a quote with its source", () => {
    render(<ConceptPage block={conceptPage("ready")} />);
    const definitions = screen.getByRole("region", { name: "Definitions" });
    expect(within(definitions).getByText(/combines retrieval with generation/)).toBeInTheDocument();
    expect(within(definitions).getByText(`${TITLE} · page 1`)).toBeInTheDocument();
  });

  it("keeps what the documents state apart from what is only named together, and words them differently", () => {
    render(<ConceptPage block={conceptPage("ready")} />);
    const links = screen.getByRole("region", { name: "Links" });
    expect(within(links).getByRole("heading", { name: "What the documents state" })).toBeInTheDocument();
    expect(within(links).getByRole("heading", { name: "Named together" })).toBeInTheDocument();
    expect(within(links).getByText(/does not say how they are related|That does not say how they are related/)).toBeInTheDocument();
    const [stated, together] = within(links).getAllByRole("list");
    // the stored relation reads with spaces, and the direction puts the other page first when it is the source
    expect(stated).toHaveTextContent("Self-RAG extended by Retrieval-Augmented Generation");
    expect(together).toHaveTextContent("large language models is named in the same sentence");
    expect(together).toHaveTextContent("1 passage");
  });

  it("says how many links are not shown", () => {
    render(<ConceptPage block={conceptPage("ready")} />);
    expect(screen.getByText(/1 more link is not shown/)).toBeInTheDocument();
  });

  it("lists claims with the pages they name and mentions with a count of the rest", () => {
    render(<ConceptPage block={conceptPage("ready")} />);
    const claims = screen.getByRole("region", { name: "Claims" });
    expect(claims).toHaveTextContent("Self-RAG extends RAG with reflection tokens.");
    expect(claims).toHaveTextContent("Names: Retrieval-Augmented Generation, Self-RAG");
    const mentions = screen.getByRole("region", { name: "Mentions" });
    expect(within(mentions).getAllByRole("listitem")).toHaveLength(2);
    expect(mentions).toHaveTextContent("Second Paper · page 4");
    expect(mentions).toHaveTextContent("3 more passages mention it.");
  });

  it("omits the Claims section when there are none and says so for an empty definitions list", () => {
    render(<ConceptPage block={conceptPage("ready", { claims: [], definitions: [] })} />);
    expect(screen.queryByRole("region", { name: "Claims" })).not.toBeInTheDocument();
    expect(screen.getByText("No sentence that defines this concept was stored.")).toBeInTheDocument();
  });

  it("renders document text as text, never as markup", () => {
    const hostile = conceptPage("ready");
    hostile.data.citations[0]!.quote = "<img src=x onerror=alert(1)> defines the concept.";
    const { container } = render(<ConceptPage block={hostile} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getAllByText(/<img src=x onerror=alert\(1\)>/).length).toBeGreaterThan(0);
  });
});

describe("ConceptPage: opening another page", () => {
  it("shows another page's name as plain text when the screen cannot open pages", () => {
    render(<ConceptPage block={conceptPage("ready")} />);
    expect(screen.queryByRole("button", { name: "Self-RAG" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Self-RAG").length).toBeGreaterThan(0);
  });

  it("makes another page's name a button that opens it, and never the page you are on", () => {
    const openPage = vi.fn();
    render(
      <NotesNav.Provider value={{ openPage }}>
        <ConceptPage block={conceptPage("ready")} />
      </NotesNav.Provider>,
    );
    fireEvent.click(screen.getAllByRole("button", { name: "Self-RAG" })[0]!);
    expect(openPage).toHaveBeenCalledWith("self_rag");
    expect(screen.queryByRole("button", { name: "Retrieval-Augmented Generation" })).not.toBeInTheDocument();
  });
});
