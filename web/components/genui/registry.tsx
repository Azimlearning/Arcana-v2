// The block registry: the only way a wire block becomes UI (constraint 2). It is typed against the
// UIBlock union, so a block type without a component is a compile error; at runtime an unregistered
// type (a server newer than this client) renders an error state instead of crashing or guessing.

import type { UIBlock } from "@arcana/schema";
import type { ComponentType } from "react";

import { ErrorState } from "./BlockStates";
import { CitedSummary } from "./CitedSummary";
import { GraphView } from "./GraphView";
import { SourceList } from "./SourceList";

/** One component per member of the block union `B`, each receiving exactly its own variant. */
export type Registry<B extends { type: string }> = {
  [K in B["type"]]: ComponentType<{ block: Extract<B, { type: K }> }>;
};

export const registry: Registry<UIBlock> = {
  CitedSummary,
  SourceList,
  GraphView,
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
