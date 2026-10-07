import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

  it("keeps every section and says so when a list is empty", () => {
    render(<ConceptPage block={conceptPage("ready", { claims: [], definitions: [] })} />);
    expect(within(screen.getByRole("region", { name: "Claims" })).getByText("No claim naming this concept was stored.")).toBeInTheDocument();
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


describe("ConceptPage: the learner's mastery", () => {
  const rated = (score: number, events: number) => conceptPage("ready", { mastery: { score, events } });

  it("says the concept is not rated yet, in words, with no meter", () => {
    render(<ConceptPage block={conceptPage("ready")} />);
    const section = screen.getByRole("region", { name: "Your mastery" });
    expect(section).toHaveTextContent("You have not rated this concept yet.");
    expect(within(section).queryByRole("meter")).not.toBeInTheDocument();
    expect(within(section).queryByRole("button")).not.toBeInTheDocument(); // the screen cannot record: no buttons
  });

  it("says where the learner stands in words and as a meter, never as a mark", () => {
    const { rerender } = render(<ConceptPage block={rated(0.7, 3)} />);
    const section = () => screen.getByRole("region", { name: "Your mastery" });
    expect(section()).toHaveTextContent("Comfortable (70 percent, from 3 ratings and answers).");
    expect(within(section()).getByRole("meter", { name: "Mastery" })).toHaveAttribute("aria-valuetext", "comfortable, 70 percent");
    rerender(<ConceptPage block={rated(0.5, 1)} />);
    expect(section()).toHaveTextContent("Getting there (50 percent, from 1 rating or answer).");
    rerender(<ConceptPage block={rated(0.3333, 2)} />);
    expect(section()).toHaveTextContent("Needs work (33 percent, from 2 ratings and answers).");
    expect(section()).toHaveTextContent("A belief that fades over a few weeks, not a mark.");
  });

  it("offers the three ratings when the screen can record them and sends the one chosen", async () => {
    const rate = vi.fn(async () => true);
    render(
      <NotesNav.Provider value={{ openPage: vi.fn(), rate }}>
        <ConceptPage block={conceptPage("ready")} />
      </NotesNav.Provider>,
    );
    const section = screen.getByRole("region", { name: "Your mastery" });
    expect(within(section).getAllByRole("button").map((b) => b.textContent)).toEqual(["I know this", "Not sure", "I don't know this yet"]);
    fireEvent.click(within(section).getByRole("button", { name: "Not sure" }));
    await waitFor(() => expect(rate).toHaveBeenCalledWith("rag", "unsure"));
    expect(within(section).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("says so, as an alert, when a rating could not be saved", async () => {
    render(
      <NotesNav.Provider value={{ openPage: vi.fn(), rate: async () => false }}>
        <ConceptPage block={conceptPage("ready")} />
      </NotesNav.Provider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "I know this" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your rating could not be saved.");
  });
});


describe("ConceptPage: rating buttons and announcements", () => {
  it("announces a change of mastery politely, as a status", () => {
    render(<ConceptPage block={conceptPage("ready", { mastery: { score: 0.7, events: 3 } })} />);
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Comfortable (70 percent, from 3 ratings and answers).");
  });

  it("keeps the focus on a rating button while it is being saved, and ignores a second press meanwhile", async () => {
    let finish: (saved: boolean) => void = () => {};
    const rate = vi.fn(() => new Promise<boolean>((resolve) => (finish = resolve)));
    render(
      <NotesNav.Provider value={{ openPage: vi.fn(), rate }}>
        <ConceptPage block={conceptPage("ready")} />
      </NotesNav.Provider>,
    );
    const button = screen.getByRole("button", { name: "I know this" });
    button.focus();
    fireEvent.click(button);
    expect(button).not.toBeDisabled(); // not disabled, so focus is not lost
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    expect(rate).toHaveBeenCalledTimes(1);
    finish(true);
    await waitFor(() => expect(button).toHaveAttribute("aria-disabled", "false"));
  });
});
