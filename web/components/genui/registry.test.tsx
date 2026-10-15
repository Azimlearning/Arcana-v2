import type { CitedSummary as CitedSummaryBlock, UIBlock } from "@arcana/schema";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { block, comparisonGrid, conceptMap, conceptPage, graphView, notesGraph, quizCard, sourceList, traversalView, docBrief, cheatSheet, learningInsights, studyPlan, studySet, verifiedLab, writingDraft } from "@/test/fixtures";

import { CitedSummary } from "./CitedSummary";
import { ComparisonGrid } from "./ComparisonGrid";
import { ConceptMap } from "./ConceptMap";
import { ConceptPage } from "./ConceptPage";
import { GraphView } from "./GraphView";
import { NotesGraph } from "./NotesGraph";
import { QuizCard } from "./QuizCard";
import { VerifiedLab } from "./VerifiedLab";
import { WritingDraft } from "./WritingDraft";
import { SourceList } from "./SourceList";
import { CheatSheet } from "./CheatSheet";
import { DocBrief } from "./DocBrief";
import { LearningInsights } from "./LearningInsights";
import { StudyPlan } from "./StudyPlan";
import { StudySet } from "./StudySet";
import { TraversalView } from "./TraversalView";
import { registry, renderBlock, type Registry } from "./registry";

describe("block registry", () => {
  it("registers a component for every block type in the wire union", () => {
    // Compile-time too: `registry: Registry<UIBlock>` fails to typecheck if a variant is missing.
    const types: UIBlock["type"][] = ["CitedSummary", "SourceList", "GraphView", "TraversalView", "ComparisonGrid", "ConceptMap", "ConceptPage", "NotesGraph", "QuizCard", "VerifiedLab", "WritingDraft", "StudySet", "StudyPlan", "DocBrief", "CheatSheet", "LearningInsights"];
    for (const type of types) expect(registry[type]).toBeTypeOf("function");
    expect(registry.CitedSummary).toBe(CitedSummary);
    expect(registry.SourceList).toBe(SourceList);
    expect(registry.GraphView).toBe(GraphView);
    expect(registry.TraversalView).toBe(TraversalView);
    expect(registry.ComparisonGrid).toBe(ComparisonGrid);
    expect(registry.ConceptMap).toBe(ConceptMap);
    expect(registry.ConceptPage).toBe(ConceptPage);
    expect(registry.NotesGraph).toBe(NotesGraph);
    expect(registry.QuizCard).toBe(QuizCard);
    expect(registry.VerifiedLab).toBe(VerifiedLab);
    expect(registry.WritingDraft).toBe(WritingDraft);
    expect(registry.StudySet).toBe(StudySet);
    expect(registry.StudyPlan).toBe(StudyPlan);
    expect(registry.DocBrief).toBe(DocBrief);
    expect(registry.CheatSheet).toBe(CheatSheet);
    expect(registry.LearningInsights).toBe(LearningInsights);
  });

  it("renders a known block through its registered component", () => {
    render(<>{renderBlock(block("ready"))}</>);
    expect(screen.getByText(/Dense retrieval embeds passages/)).toBeInTheDocument();
  });

  it("renders a SourceList block through the registry", () => {
    render(<>{renderBlock(sourceList("ready"))}</>);
    expect(screen.getByText("BM25 in Practice")).toBeInTheDocument();
  });

  it("renders a GraphView block through the registry", () => {
    render(<>{renderBlock(graphView("ready"))}</>);
    expect(screen.getByRole("group", { name: /Graph of 3 concepts and 2 relations/ })).toBeInTheDocument();
  });

  it("renders a TraversalView block through the registry", () => {
    render(<>{renderBlock(traversalView("ready"))}</>);
    expect(screen.getByRole("group", { name: /Search path of 3 concepts and 2 steps/ })).toBeInTheDocument();
  });

  it("renders a ConceptPage and a NotesGraph block through the registry", () => {
    render(<>{renderBlock(conceptPage("ready"))}</>);
    expect(screen.getByRole("article", { name: "Retrieval-Augmented Generation" })).toBeInTheDocument();
    render(<>{renderBlock(notesGraph("ready"))}</>);
    expect(screen.getByRole("group", { name: /Page graph of 3 pages/ })).toBeInTheDocument();
  });

  it("renders a QuizCard block through the registry", () => {
    render(<>{renderBlock(quizCard("ready"))}</>);
    expect(screen.getByRole("region", { name: "Quiz questions" })).toBeInTheDocument();
  });

  it("renders a VerifiedLab block through the registry (the code only in a sandboxed iframe)", async () => {
    render(<>{renderBlock(verifiedLab("ready"))}</>);
    expect(screen.getByRole("region", { name: "Lab" })).toBeInTheDocument();
    expect(await screen.findByTitle(/^Lab: /)).toHaveAttribute("sandbox", "allow-scripts");
  });

  it("renders a WritingDraft block through the registry", () => {
    render(<>{renderBlock(writingDraft("ready"))}</>);
    expect(screen.getByRole("region", { name: "Draft" })).toBeInTheDocument();
  });

  it("renders a StudySet block through the registry", () => {
    render(<>{renderBlock(studySet("ready"))}</>);
    expect(screen.getByRole("region", { name: "Study items" })).toBeInTheDocument();
  });

  it("renders a StudyPlan block through the registry", () => {
    render(<>{renderBlock(studyPlan("ready"))}</>);
    expect(screen.getByRole("region", { name: "Review schedule" })).toBeInTheDocument();
  });

  it("renders a LearningInsights block through the registry", () => {
    render(<>{renderBlock(learningInsights("ready"))}</>);
    expect(screen.getByRole("region", { name: "Mastery" })).toBeInTheDocument();
  });

  it("renders a CheatSheet block through the registry", () => {
    render(<>{renderBlock(cheatSheet("ready"))}</>);
    expect(screen.getByRole("img", { name: "Concept diagram" })).toBeInTheDocument();
  });

  it("renders a DocBrief block through the registry", () => {
    render(<>{renderBlock(docBrief("ready"))}</>);
    expect(screen.getByRole("region", { name: "Key points" })).toBeInTheDocument();
  });

  it("renders a ComparisonGrid block through the registry", () => {
    render(<>{renderBlock(comparisonGrid("ready"))}</>);
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("renders a ConceptMap block through the registry", () => {
    render(<>{renderBlock(conceptMap("ready"))}</>);
    expect(screen.getByRole("list", { name: "Steps" })).toBeInTheDocument();
  });

  it("an unregistered block type renders an error state, never a crash or a blank", () => {
    const fromANewerServer = { ...block("ready"), type: "TimelineRibbon" } as unknown as UIBlock;
    render(<>{renderBlock(fromANewerServer)}</>);
    expect(screen.getByRole("alert")).toHaveTextContent('cannot display blocks of type "TimelineRibbon"');
  });

  it("a block with no type at all is also an error state", () => {
    render(<>{renderBlock({} as UIBlock)}</>);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});

// A registry must cover its whole union. This is checked by the compiler, not at runtime:
// `pnpm typecheck` fails if the @ts-expect-error below stops being an error, i.e. if the Registry
// type ever stops requiring every member of the union.
type FutureBlock = { type: "TimelineRibbon"; id: string };

describe("Registry<B> typing", () => {
  it("rejects a registry that omits a member of the union", () => {
    // @ts-expect-error: "TimelineRibbon" has no component, so this must not compile
    const incomplete: Registry<CitedSummaryBlock | FutureBlock> = { CitedSummary };
    expect(incomplete).toBeDefined();
  });

  it("accepts a registry that covers every member", () => {
    const complete: Registry<CitedSummaryBlock | FutureBlock> = {
      CitedSummary,
      TimelineRibbon: () => null,
    };
    expect(Object.keys(complete)).toEqual(["CitedSummary", "TimelineRibbon"]);
  });
});
