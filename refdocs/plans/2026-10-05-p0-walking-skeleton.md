# Plan: P0 Walking skeleton + eval harness

> Phase P0 of `refdocs/arcana-v2-PRD.md` §6. Execution doc: `refdocs/execution/2026-10-05-p0-walking-skeleton.md`.
> A plan says **what and why**. The execution doc says **how and in what order**. Keep them separate; when they merge, both stop being read.

## Why this exists

Every later phase depends on four contracts that are cheap to get right now and expensive to fix
later: the wire schema shared by `api/` and `web/`, the storage abstractions, the hybrid retrieval
function with independently switchable signals, and the eval harness that measures it. v1 proved the
order works (its P0 skeleton de-risked codegen, SSE and the LangGraph join before anything depended
on them). P0 rebuilds that spine for v2: one PDF in, one cited answer rendered, one metrics file out.

The eval harness is in P0, not later, because v1's evidence gap (null pilot, no gold set, quota
death) came from treating evaluation as a final step.

## What's already covered (no work needed)

- **Design decisions:** stack (D-03), storage (D-09), embeddings (D-14), metrics (D-15), all logged.
- **Reference implementations in v1** (read, then rewrite or port with provenance per D-01, D-16):
  - schema codegen: `../Arcana/packages/schema/codegen/to_python.ts` (ts-morph, `--check` mode)
  - retrieval and fusion: `../Arcana/api/retrieval/`
  - stream consumer: `../Arcana/web/lib/stream.ts`
  - the `CitedSummary` component: `../Arcana/web/components/genui/CitedSummary.tsx`
  - eval: `../Arcana/eval/questions.yaml` (pre-registered 9 Jun 2026), `eval/corpus/MANIFEST.json`,
    `eval/run_ablation.py`, `eval/extraction_audit.py`
- **Benchmark settings** from the paper's settings table: chunk 1,200 / overlap 200, 3,072-dim cosine,
  BM25 over the same chunks, schema-free extraction one pass per chunk, RRF k = 60, top 10 per signal
  and after fusion, 1-hop graph traversal from resolved query entities.

## Scope

**In:**
- pnpm workspace (`web`, `packages/schema`) and a uv project (`api`); one root command per check
- `packages/schema`: `UIBlock` union with `CitedSummary` as the only variant, `BlockMeta`, the error
  envelope; codegen to Python; a drift check
- `api/core`: typed settings (fails loudly on a missing required key), structured logging, error
  envelope, per-turn token budget
- `api/llm`: one seam, Anthropic primary, OpenRouter fallback, model tiers, a spend ledger, and a
  monthly cap check before each call
- `api/stores`: `GraphStore`, `VectorStore`, `DocStore` abstractions and local implementations
- `api/ingestion`: PDF parse, chunk, embed, extract; graph edges record their source chunk id
- `api/retrieval`: dense, BM25, graph, RRF; each signal switchable; approximate query entity
  resolution, with the resolution hit rate logged per query
- One agent (Research) producing one `CitedSummary`, validated server-side (fail closed), streamed
  over SSE; LangGraph wired with the single node so later agents slot in
- `web/`: Next.js app, stream consumer, registry, `CitedSummary` with all four states, an upload box
  and a question box
- `eval/`: question set and corpus manifest carried from v1 (Q-05), a gold-annotation file format, a
  five-arm runner (dense, sparse, graph, flat, hybrid), RAGAS non-LLM context metrics, results as JSON

**Out (and why):**
- More agents, `route_to_agent`, the Fact Checker: P1. The skeleton needs one node, not a graph.
- More components, the Composer, `LayoutSpec`: P2.
- Trained engines: P3. Only the `Engine` interface location is reserved.
- VerifiedLab, the lifecycle: P4.
- Writing the gold annotations themselves: P1 (the format and the tooling are P0).
- The full 16-document benchmark run: P1 exit criterion. P0 runs a smoke subset.
- Deploy config: deferred (D-13).

## Approach

Vertical first, then each layer to its P0 depth. Build the thinnest path: a fixture PDF through
every layer to a rendered block, with fakes where a real service would cost money (a fake LLM and
fake embeddings behind the same interfaces, selected by settings). Then replace fakes with real
providers one at a time, behind the spend cap.

Before using any library whose API changed since v1 (Next.js, React, Tailwind, LangGraph, RAGAS),
read its current docs; do not copy v1 usage.

The vector store is a spike: try the candidates against 3,072-dim vectors on this Windows machine,
pick one, record it as an ADR (resolving Q-02), and put it behind `VectorStore` so the choice stays
cheap to change.

## Risks & unknowns

| Risk / unknown | Confidence | Mitigation |
|---|---|---|
| Local vector store fit (Q-02) | Low: not yet tried | Spike first; `VectorStore` interface isolates the choice |
| Python 3.13 vs 3.12 (Q-03) | Low: v1's reason unrecorded | Try 3.13 with the dependency set; fall back to 3.12 via uv |
| LangGraph API changed since v1's `<0.3` pin | Medium: v1 code read, current docs not yet | Read current docs before wiring the node |
| RAGAS API surface | Medium: current docs read for non-LLM context metrics (2026-10-05) | Wrap RAGAS calls in one module of `eval/` |
| Spend cap value unknown (Q-01) | n/a | Fakes until Azim sets it; no paid call before |
| Entity resolution again fails to fire | Medium: the pilot's failure mode | Log resolution hit rate per query from day one; it is a P0 output, not a P1 surprise |

## Definition of done

This phase is done when every line below is true and has been *observed*, not assumed:

- [ ] A fixture PDF uploaded through the web UI produces a `CitedSummary` rendered in the browser, with at least one citation that names the source document.
- [ ] The same request with the LLM forced to fail produces the error state, not a blank or partial render.
- [ ] A malformed block constructed in a test is rejected by the server validator with a structured error naming the field path.
- [ ] The codegen drift check passes, and fails when a schema field is changed without regenerating.
- [ ] Backend tests, frontend tests, lint and type checks all pass from the root commands.
- [ ] Each retrieval signal can be disabled independently, shown by a test per arm.
- [ ] The eval runner writes a metrics JSON for all five arms on at least two questions, including RAGAS non-LLM context recall/precision against a hand-made gold entry, and the per-query entity-resolution hit rate.
- [ ] The spend ledger records every paid call, and a call that would exceed the cap is refused before it is sent.
