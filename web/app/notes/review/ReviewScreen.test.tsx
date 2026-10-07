// The review screen against a mocked server: the four lists in words, the exact totals beyond what is shown, and the states.

import type { VaultLintResponse } from "@arcana/schema";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { envelope, jsonResponse } from "@/test/fixtures";

import { ReviewScreen } from "./ReviewScreen";

const ref = (id: string, label: string, passages = 1) => ({ id, label, passages });

const report = (over: Partial<VaultLintResponse> = {}): VaultLintResponse => ({
  pages: 40,
  orphans: [ref("banana", "banana"), ref("dense", "dense retrieval", 3)],
  orphansTotal: 2,
  duplicates: [
    { a: ref("dr", "dense retrieval", 3), b: ref("drs", "Dense Retrievals"), reason: "same_name" },
    { a: ref("llm", "large language models", 5), b: ref("lm", "language models", 2), reason: "one_more_word" },
  ],
  duplicatesTotal: 2,
  tensions: [
    {
      page: ref("rag", "RAG", 6),
      definitions: [
        { docTitle: "Paper One", text: "RAG combines retrieval with generation." },
        { docTitle: "Paper Two", text: "RAG <b>grounds</b> a model in documents." },
      ],
    },
  ],
  tensionsTotal: 1,
  hubs: [ref("retrieval", "retrieval", 30)],
  ...over,
});

let answer: () => Response;

beforeEach(() => {
  answer = () => jsonResponse(report());
  vi.stubGlobal("fetch", vi.fn(async () => answer()));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ReviewScreen", () => {
  it("says it is a report, and lists near-duplicate pages with the reason in words", async () => {
    render(<ReviewScreen />);
    const section = await screen.findByRole("region", { name: "Concepts that two names may describe" });
    expect(screen.getByText(/nothing here is changed for you/)).toBeInTheDocument();
    expect(section).toHaveTextContent("dense retrieval · 3 passages and Dense Retrievals · 1 passage");
    expect(section).toHaveTextContent("the same words once plurals and hyphens are ignored");
    expect(section).toHaveTextContent("one name is the other with one more word");
    expect(screen.queryByRole("button")).not.toBeInTheDocument(); // reported, never fixed: no action here
  });

  it("puts the definitions of a concept several papers define side by side, as text and with the paper", async () => {
    render(<ReviewScreen />);
    const section = await screen.findByRole("region", { name: "Concepts several papers define" });
    expect(section.querySelectorAll("blockquote")).toHaveLength(2);
    expect(section).toHaveTextContent("Paper One");
    expect(section).toHaveTextContent("Paper Two");
    expect(section).toHaveTextContent("RAG <b>grounds</b> a model in documents."); // text, never markup
    expect(section.querySelector("b")).toBeNull();
  });

  it("lists pages no link reaches and pages named almost everywhere", async () => {
    render(<ReviewScreen />);
    expect(await screen.findByRole("region", { name: "Concepts no link reaches" })).toHaveTextContent("banana");
    expect(screen.getByRole("region", { name: "Pages named almost everywhere" })).toHaveTextContent("retrieval · 30 passages");
  });

  it("gives the exact total and says how many are not shown when the server capped a list", async () => {
    answer = () => jsonResponse(report({ orphansTotal: 130 }));
    render(<ReviewScreen />);
    const section = await screen.findByRole("region", { name: "Concepts no link reaches" });
    expect(section).toHaveTextContent("(130)");
    expect(section).toHaveTextContent("128 more are not shown (the list stops at 2).");
  });

  it("says so in words when a list is empty", async () => {
    answer = () => jsonResponse(report({ tensions: [], tensionsTotal: 0 }));
    render(<ReviewScreen />);
    expect(await screen.findByRole("region", { name: "Concepts several papers define" })).toHaveTextContent("Nothing to look at here.");
  });

  it("with no pages yet, says there is nothing to review", async () => {
    answer = () =>
      jsonResponse(report({ pages: 0, orphans: [], orphansTotal: 0, duplicates: [], duplicatesTotal: 0, tensions: [], tensionsTotal: 0, hubs: [] }));
    render(<ReviewScreen />);
    expect(await screen.findByText(/There are no pages yet, so nothing to review/)).toBeInTheDocument();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("shows a busy status while it reads, and the server's reason as an alert when it cannot", async () => {
    answer = () => jsonResponse(envelope({ code: "internal", message: "The vault is unreadable.", retryable: true }), 500);
    render(<ReviewScreen />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(await screen.findByRole("alert")).toHaveTextContent("The vault is unreadable.");
  });

  it("links back to the notes and to the chat, and marks itself as the current view", async () => {
    render(<ReviewScreen />);
    await screen.findByRole("region", { name: "Concepts no link reaches" });
    expect(screen.getByRole("link", { name: "Notes" })).toHaveAttribute("href", "/notes");
    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Review" })).toHaveAttribute("aria-current", "page");
  });
});
