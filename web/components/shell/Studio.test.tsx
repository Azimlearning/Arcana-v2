import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { STARTERS, Studio } from "./Studio";

describe("Studio", () => {
  it("lists the tools the Studio agent has, in order, each a button, and a link to the notes", () => {
    render(<Studio onStart={() => {}} />);
    const buttons = within(screen.getByRole("region", { name: "Studio" })).getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual([
      "Quiz meFill the blank",
      "FlashcardsName a topic",
      "BlurtingRecall, then check",
      "Cornell notesName a topic",
      "Socratic questionsName a topic",
      "Review scheduleWhat is due",
      "Document briefKey points, next steps",
      "Write an outlineName a topic",
      "Literature reviewCited, by theme",
      "AbstractCited, short",
      "Audio overviewA script to listen to",
    ]);
    expect(screen.getByRole("link", { name: /Notes/ })).toHaveAttribute("href", "/notes");
  });

  it("a tool that needs a topic puts its opening words in the question box and does not ask", () => {
    const onStart = vi.fn();
    render(<Studio onStart={onStart} />);
    fireEvent.click(screen.getByRole("button", { name: /Flashcards/ }));
    expect(onStart).toHaveBeenCalledWith("Make flashcards for ", false);
  });

  it("the review schedule is asked at once", () => {
    const onStart = vi.fn();
    render(<Studio onStart={onStart} />);
    fireEvent.click(screen.getByRole("button", { name: /Review schedule/ }));
    expect(onStart).toHaveBeenCalledWith("What should I review today?", true);
  });

  it("with no handler (a screen that cannot ask) the tools are disabled, not silently dead", () => {
    render(<Studio />);
    for (const button of screen.getAllByRole("button")) expect(button).toBeDisabled();
  });

  it("every starter opens with words the server's rules recognise, so none is a plain question", () => {
    const writes = /^(write|draft|compose|outline|make an audio overview)/i;
    const studies = /^(quiz me|brief me|make flashcards|make a blurting|give me cornell|guide me|what should i review)/i;
    for (const s of STARTERS) expect(writes.test(s.request) || studies.test(s.request)).toBe(true);
  });
});
