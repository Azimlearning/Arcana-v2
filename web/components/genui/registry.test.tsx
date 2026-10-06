import type { CitedSummary as CitedSummaryBlock, UIBlock } from "@arcana/schema";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { block, comparisonGrid, conceptMap, graphView, sourceList } from "@/test/fixtures";

import { CitedSummary } from "./CitedSummary";
import { ComparisonGrid } from "./ComparisonGrid";
import { ConceptMap } from "./ConceptMap";
import { GraphView } from "./GraphView";
import { SourceList } from "./SourceList";
import { registry, renderBlock, type Registry } from "./registry";

describe("block registry", () => {
  it("registers a component for every block type in the wire union", () => {
    // Compile-time too: `registry: Registry<UIBlock>` fails to typecheck if a variant is missing.
    const types: UIBlock["type"][] = ["CitedSummary", "SourceList", "GraphView", "ComparisonGrid", "ConceptMap"];
    for (const type of types) expect(registry[type]).toBeTypeOf("function");
    expect(registry.CitedSummary).toBe(CitedSummary);
    expect(registry.SourceList).toBe(SourceList);
    expect(registry.GraphView).toBe(GraphView);
    expect(registry.ComparisonGrid).toBe(ComparisonGrid);
    expect(registry.ConceptMap).toBe(ConceptMap);
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
