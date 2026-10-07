import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TITLE, envelope, quizAnswer, quizCard } from "@/test/fixtures";

import { NotesNav, type NotesNavValue } from "./notesNav";
import { QuizCard } from "./QuizCard";

const withNav = (value: Partial<NotesNavValue>, ui = <QuizCard block={quizCard("ready")} />) =>
  render(<NotesNav.Provider value={{ openPage: vi.fn(), ...value }}>{ui}</NotesNav.Provider>);

describe("QuizCard: the wire states", () => {
  it("loading: a busy status and no questions", () => {
    render(<QuizCard block={quizCard("loading")} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("region", { name: "Quiz questions" })).not.toBeInTheDocument();
  });

  it("empty with no claims: says why in words, and is not announced as a failure", () => {
    render(<QuizCard block={quizCard("empty")} />);
    expect(screen.getByText("No question could be made.")).toBeInTheDocument();
    expect(screen.getByText(/hold no claims to ask about/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("empty after looking at sentences: says how many were looked at", () => {
    const { unmount } = render(<QuizCard block={quizCard("empty", { skipped: 3 })} />);
    expect(screen.getByText(/3 sentences were looked at, and none could be turned into a fair question/)).toBeInTheDocument();
    unmount();
    render(<QuizCard block={quizCard("empty", { skipped: 1 })} />);
    expect(screen.getByText(/1 sentence was looked at/)).toBeInTheDocument();
  });

  it("error: shows the reason from meta.error as an alert", () => {
    render(<QuizCard block={quizCard("error", {}, envelope({ message: "The vault is unreadable." }))} />);
    expect(within(screen.getByRole("alert")).getByText("The vault is unreadable.")).toBeInTheDocument();
  });

  it("partial: shows what is there and says it is not final", () => {
    render(<QuizCard block={quizCard("partial")} />);
    expect(screen.getByRole("region", { name: "Quiz questions" })).toBeInTheDocument();
    expect(screen.getByText(/not final/i)).toBeInTheDocument();
  });
});

describe("QuizCard: ready, before any answer", () => {
  it("shows each sentence with its blank read out as 'blank', four choices and where it is from", () => {
    render(<QuizCard block={quizCard("ready")} />);
    const region = screen.getByRole("region", { name: "Quiz questions" });
    const questions = within(region).getAllByRole("listitem");
    expect(questions).toHaveLength(2);
    expect(questions[0]).toHaveTextContent("blank finds passages by comparing embedding vectors of the query and the text.");
    expect(questions[0]).toHaveTextContent(`From ${TITLE} · page 3`);
    expect(questions[1]).toHaveTextContent(`From ${TITLE}`);
    expect(questions[1]).not.toHaveTextContent("page");
    const groups = within(region).getAllByRole("group", { name: "Answer choices" });
    expect(groups).toHaveLength(2);
    expect(groups[0]).toHaveTextContent("BM25dense retrievalrerankingreciprocal rank fusion");
  });

  it("does not say which choice is right, and draws plain choices (no buttons) when the screen cannot check an answer", () => {
    render(<QuizCard block={quizCard("ready")} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText(/the answer/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Open the notes screen to answer/)).toBeInTheDocument();
  });

  it("renders the document's text as text, never as markup", () => {
    const text = '_____ is <img src=x onerror="alert(1)"> **bold** in this sentence here.';
    const { container } = render(<QuizCard block={quizCard("ready", { items: [{ ...quizCard("ready").data.items[0]!, text }] })} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container).toHaveTextContent('<img src=x onerror="alert(1)">');
  });

  it("says how many sentences were passed over, and that a cloze tests recognition, not understanding", () => {
    render(<QuizCard block={quizCard("ready", { skipped: 4 })} />);
    expect(screen.getByText(/4 sentences were passed over/)).toBeInTheDocument();
    expect(screen.getByText(/tests recognising a name in a sentence, not understanding it/)).toBeInTheDocument();
  });

  it("with a focus page, drops the 'know least' wording that only fits a quiz across the vault", () => {
    const { unmount } = render(<QuizCard block={quizCard("ready", { focusId: "bm25" })} />);
    expect(screen.queryByText(/know least/)).not.toBeInTheDocument();
    unmount();
    render(<QuizCard block={quizCard("ready")} />);
    expect(screen.getByText(/starting with the ones you know least/)).toBeInTheDocument();
  });
});

describe("QuizCard: answering", () => {
  it("offers the choices as buttons and sends the item and the choice to the screen", async () => {
    const answer = vi.fn(async () => quizAnswer());
    withNav({ answer });
    const first = screen.getAllByRole("group", { name: "Answer choices" })[0]!;
    expect(within(first).getAllByRole("button")).toHaveLength(4);
    fireEvent.click(within(first).getByRole("button", { name: "dense retrieval" }));
    await waitFor(() => expect(answer).toHaveBeenCalledWith("claim-1~dense_retrieval", "dense_retrieval"));
  });

  it("a right answer is announced politely, fills the blank, shows the source and the mastery in words", async () => {
    withNav({ answer: async () => quizAnswer() });
    const first = screen.getAllByRole("listitem")[0]!;
    fireEvent.click(within(first).getByRole("button", { name: "dense retrieval" }));
    expect(await within(first).findByText("Correct.")).toBeInTheDocument();
    expect(first).toHaveTextContent("dense retrieval finds passages by comparing embedding vectors");
    expect(within(first).getByRole("button", { name: "dense retrieval (the answer)" })).toBeInTheDocument();
    expect(first).toHaveTextContent(`${TITLE} · page 3`);
    expect(first).toHaveTextContent("Your mastery of dense retrieval: getting there (67 percent, from 1 rating or answer).");
    expect(within(first).getAllByRole("status").some((s) => s.getAttribute("aria-live") === "polite")).toBe(true);
  });

  it("a wrong answer says which one was right and which was chosen, in words and not by colour alone", async () => {
    withNav({ answer: async () => quizAnswer({ correct: false, mastery: { score: 0.3333, events: 1 } }) });
    const first = screen.getAllByRole("listitem")[0]!;
    fireEvent.click(within(first).getByRole("button", { name: "BM25" }));
    expect(await within(first).findByText("Not quite. The answer is dense retrieval.")).toBeInTheDocument();
    expect(within(first).getByRole("button", { name: "BM25 (your choice)" })).toBeInTheDocument();
    expect(within(first).getByRole("button", { name: "dense retrieval (the answer)" })).toBeInTheDocument();
    expect(first).toHaveTextContent("needs work (33 percent");
  });

  it("keeps focus on a button while the choice is checked and ignores a second press meanwhile", async () => {
    let release: (value: ReturnType<typeof quizAnswer>) => void = () => {};
    const answer = vi.fn(() => new Promise<ReturnType<typeof quizAnswer>>((resolve) => (release = resolve)));
    withNav({ answer });
    const first = screen.getAllByRole("listitem")[0]!;
    const button = within(first).getByRole("button", { name: "BM25" });
    button.focus();
    fireEvent.click(button);
    expect(within(first).getByText("Checking…")).toBeInTheDocument();
    fireEvent.click(within(first).getByRole("button", { name: "reranking" }));
    expect(answer).toHaveBeenCalledTimes(1);
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(document.activeElement).toBe(button);
    release(quizAnswer());
    await within(first).findByText("Correct.");
  });

  it("says so, as an alert, when the choice could not be checked, and lets the learner choose again", async () => {
    const answer = vi.fn().mockResolvedValueOnce(null).mockResolvedValueOnce(quizAnswer());
    withNav({ answer });
    const first = screen.getAllByRole("listitem")[0]!;
    fireEvent.click(within(first).getByRole("button", { name: "BM25" }));
    expect(await within(first).findByRole("alert")).toHaveTextContent("Your answer could not be checked.");
    expect(within(first).queryByRole("button", { name: "More questions" })).not.toBeInTheDocument(); // no screen action offered here
    fireEvent.click(within(first).getByRole("button", { name: "dense retrieval" }));
    expect(await within(first).findByText("Correct.")).toBeInTheDocument();
    expect(answer).toHaveBeenCalledTimes(2);
  });

  it("once every question is answered, gives the score and offers more questions", async () => {
    const moreQuestions = vi.fn();
    const answer = vi.fn(async (itemId: string) =>
      itemId === "claim-1~dense_retrieval"
        ? quizAnswer()
        : quizAnswer({ itemId, correct: false, answer: { id: "bm25", label: "BM25" } }),
    );
    withNav({ answer, moreQuestions });
    expect(screen.queryByRole("button", { name: "More questions" })).not.toBeInTheDocument();
    const [one, two] = screen.getAllByRole("listitem");
    fireEvent.click(within(one!).getByRole("button", { name: "dense retrieval" }));
    await within(one!).findByText("Correct.");
    expect(screen.queryByText(/You got/)).not.toBeInTheDocument();
    fireEvent.click(within(two!).getByRole("button", { name: "reranking" }));
    await within(two!).findByText(/Not quite/);
    expect(screen.getByText("You got 1 of 2.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "More questions" }));
    expect(moreQuestions).toHaveBeenCalledTimes(1);
  });

  it("a new quiz starts with no answers carried over", async () => {
    const answer = async () => quizAnswer();
    const { rerender } = withNav({ answer });
    const first = screen.getAllByRole("listitem")[0]!;
    fireEvent.click(within(first).getByRole("button", { name: "dense retrieval" }));
    await within(first).findByText("Correct.");
    const next = quizCard("ready");
    next.data.items = [{ ...next.data.items[1]!, id: "claim-9~bm25" }];
    rerender(
      <NotesNav.Provider value={{ openPage: vi.fn(), answer }}>
        <QuizCard block={next} />
      </NotesNav.Provider>,
    );
    expect(screen.queryByText("Correct.")).not.toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });
});

describe("QuizCard: the answer must not show before it is chosen", () => {
  it("draws every blank of a sentence and fills every one once answered", async () => {
    const base = quizCard("ready").data.items[0]!;
    const text = "_____ ranks passages, and _____ is the usual form of _____ in search engines.";
    withNav({ answer: async () => quizAnswer() }, <QuizCard block={quizCard("ready", { items: [{ ...base, text }] })} />);
    const item = screen.getByRole("listitem");
    expect(item).toHaveTextContent("blank ranks passages, and blank is the usual form of blank in search engines.");
    fireEvent.click(within(item).getByRole("button", { name: "dense retrieval" }));
    await within(item).findByText("Correct.");
    expect(item).toHaveTextContent("dense retrieval ranks passages, and dense retrieval is the usual form of dense retrieval in search engines.");
  });

  it("says 'a document' when the server left a revealing title out", () => {
    const base = quizCard("ready").data.items[0]!;
    render(<QuizCard block={quizCard("ready", { items: [{ ...base, docTitle: "" }] })} />);
    expect(screen.getByRole("listitem")).toHaveTextContent("From a document · page 3");
  });

  it("offers more questions beside a failed answer when the screen can ask for them", async () => {
    const moreQuestions = vi.fn();
    withNav({ answer: async () => null, moreQuestions });
    const first = screen.getAllByRole("listitem")[0]!;
    fireEvent.click(within(first).getByRole("button", { name: "BM25" }));
    const alert = await within(first).findByRole("alert");
    fireEvent.click(within(alert).getByRole("button", { name: "More questions" }));
    expect(moreQuestions).toHaveBeenCalledTimes(1);
  });
});

