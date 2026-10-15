// The block registry: the only way a wire block becomes UI (constraint 2). It is typed against the
// UIBlock union, so a block type without a component is a compile error; at runtime an unregistered
// type (a server newer than this client) renders an error state instead of crashing or guessing.

import type { UIBlock } from "@arcana/schema";
import type { ComponentType } from "react";

import { ErrorState } from "./BlockStates";
import { CitedSummary } from "./CitedSummary";
import { ComparisonGrid } from "./ComparisonGrid";
import { ConceptMap } from "./ConceptMap";
import { ConceptPage } from "./ConceptPage";
import { DocBrief } from "./DocBrief";
import { GraphView } from "./GraphView";
import { NotesGraph } from "./NotesGraph";
import { QuizCard } from "./QuizCard";
import { SourceList } from "./SourceList";
import { StudyPlan } from "./StudyPlan";
import { StudySet } from "./StudySet";
import { TraversalView } from "./TraversalView";
import { VerifiedLab } from "./VerifiedLab";
import { WritingDraft } from "./WritingDraft";

/** One component per member of the block union `B`, each receiving exactly its own variant. */
export type Registry<B extends { type: string }> = {
  [K in B["type"]]: ComponentType<{ block: Extract<B, { type: K }> }>;
};

export const registry: Registry<UIBlock> = {
  CitedSummary,
  SourceList,
  GraphView,
  TraversalView,
  ComparisonGrid,
  ConceptMap,
  ConceptPage,
  NotesGraph,
  QuizCard,
  VerifiedLab,
  WritingDraft,
  StudySet,
  StudyPlan,
  DocBrief,
};

export function UnknownBlock({ type }: { type: string }) {
  return (
    <ErrorState
      error={{
        code: "validation_failed",
        message: `This client cannot display blocks of type "${type}".`,
        issues: [],
        retryable: false,
      }}
      fallback="Unknown block."
    />
  );
}

export function renderBlock(block: UIBlock) {
  const Component = (registry as Record<string, ComponentType<{ block: UIBlock }> | undefined>)[block.type];
  if (!Component) return <UnknownBlock type={String(block.type)} />;
  return <Component block={block} />;
}
