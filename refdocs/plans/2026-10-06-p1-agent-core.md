# Plan: P1 Agent core with super tools + first full benchmark

> Phase P1 of `refdocs/arcana-v2-PRD.md` §6. Execution doc: `refdocs/execution/2026-10-06-p1-agent-core.md`.
> A plan says **what and why**. The execution doc says **how and in what order**.

## Why this exists

P0 proved the spine with one agent and one block. P1 does the two things the research claim rests on:

1. **A real agent layer.** Several agents that compose only through `route_to_agent`, inside hop and
   token budgets, always ending at the Composer, with a Fact Checker that fails closed. This is pillar 1
   of the architecture (D-02, D-05).
2. **The first evidence.** The graph-versus-flat benchmark that v1 never produced (its pilot was null,
   had no gold set, and died on a quota). P0 built the harness; P1 supplies gold annotation, a live
   corpus and the paired test, then reports whatever the numbers are, including a null.

## What's already covered (no work needed)

- **From P0:** the LLM seam with ledger and cap, three stores, ingestion, the three retrievers and RRF,
  the five ablation arms and their frozen protocol (D-20), the fail-closed validator, the Composer stub,
  the LangGraph turn graph with runtime context, the SSE stream, the web shell, and the eval runner.
- **Reference in v1 (read, then port with provenance or rewrite):**
  - `../Arcana/api/agents/base.py`: `route_to_agent` charging a hop budget and returning a `partial`
    result when it is exceeded; the `@tool` decorator deriving a JSON schema from a signature.
    Port the shape; **do not port the global `registry`** (hidden state; v2 passes an explicit roster).
  - `../Arcana/api/agents/tier2/{cross_doc,graph_agent,comparator}.py`, `tier4/fact_checker.py`: read for
    what the tools should do; rewrite against v2's stores and types.
  - `../Arcana/eval/extraction_audit.py`: reference for the extraction audit (not in P1 scope, below).
- **Not reusable:** v1's 25-agent graph and five-mode UI (D-01, D-05).

## Scope

**In:**
- **Roster decision (resolves Q-04, new ADR).** Built in P1: Orchestrator, Research, Graph, Fact Checker,
  plus the existing Composer stub. Tutor and Lab Builder stay in the roster but are built later
  (Lab Builder P4, Tutor and Writer P5).
- **Agent framework:** an explicit `Roster`, typed tools with generated JSON schemas, `route_to_agent`
  with hop and token budgets and a loop guard, and a guarantee that every turn ends at the Composer even
  on budget exhaustion or failure.
- **Super tools** (each does substantial work, none wraps a prompt):
  - Research: `retrieve_evidence`, `compare_documents` (evidence grouped per document for a
    cross-document question), supporting quotes chosen by the model and verified verbatim.
  - Graph: `find_path` between entities and `neighborhood` of an entity, every edge carrying the chunk
    it came from.
  - Fact Checker: verbatim quote check, claim-support check (judge model different from the generator,
    with a deterministic lexical fallback), fail closed.
- **Orchestrator routing:** deterministic intent rules, with one LLM routing call when the rules are not
  confident. The trained router is P3.
- **Turn trace:** a `TurnTrace` wire type recorded per turn, served by an endpoint, and shown in a small
  web panel, so a multi-agent request can be traced end to end (the PRD exit criterion).
- **Gold annotation for all 20 questions**, drafted from the papers and approved by Azim, and the
  decision on q-single-01 (ADR D-21).
- **A live corpus:** the 16 papers ingested once with real embeddings and real extraction.
- **The first full benchmark:** five arms over 20 questions, a paired Wilcoxon test, results committed.

**Out, with reasons:**
- New GenUI components, the real Composer and `LayoutSpec`: P2. P1 keeps the one block type so the
  agent layer is not entangled with the catalog.
- Trained tools (router distillation, Re-Rank): P3. P1's router is rules plus one LLM call.
- VerifiedLab and the lifecycle: P4. A small mutation suite for the Fact Checker is in; the full
  verifier mutation suite is P4.
- Tutor and Writer depth: P5.
- RAGAS faithfulness and any model-judged answer quality: P5. It would confound retrieval with
  generation (D-15) and costs a generation per arm.
- A full extraction audit and chat memory: P5. P1 records extraction failures and entity-resolution
  rates only.

## Approach

Two tracks. **Track A** (agent layer, tasks A1 to A9) needs no keys: it runs on fakes and can start now.
**Track B** (gold, live corpus, benchmark, tasks B1 to B6) needs Azim's keys, a larger cap, free disk and
his review of the gold, so it follows Track A and waits on him. The order inside Track A is schema first
(`TurnTrace`), then the framework, then one agent at a time, then the multi-agent request. Before using
LangGraph's dynamic routing, read its current docs; do not copy v1's usage (rule 6).

Gold is written from the papers by keyword search of the PDF text, never by looking at what retrieval
returns, so the gold cannot be shaped by the system it will judge. The method is recorded in the gold
README, and Azim approves each file before it is frozen.

## Cost estimate (live benchmark)

The corpus is 1,570 chunks. Extraction runs on the light tier (Claude Haiku 4.5, $1 and $5 per million
tokens in and out). Per chunk about 480 input tokens (system prompt plus 1,200 characters) and 250 to
600 output tokens, so about $0.002 to $0.0035 per chunk:

| Item | Estimate |
|---|---|
| Extraction, 1,570 chunks | about $3.9 (range $2.5 to $5.5) |
| Embeddings, about 470k tokens at an assumed $0.13 per million | about $0.06 |
| Query embeddings, 20 questions | under $0.01 |
| **Total for the one-shot ingestion and benchmark** | **about $4 (range $2.6 to $5.6)** |

The $5 cap sits inside that range, so a run could be refused part-way (the pipeline removes the partly
ingested document cleanly, but the money spent is gone and extraction is not reproducible). Recommend
raising the cap to $10 for this run. The estimate is built from character counts; task B2 ingests one
real paper first and extrapolates from the measured cost before the full run. `cost-auditor` reviews
before any paid run.

## Risks & unknowns

| Risk / unknown | Confidence | Mitigation |
|---|---|---|
| LangGraph dynamic routing API (conditional edges, `Command`, subgraphs) | Medium: P0 used only a linear graph | Read current docs first (A1); keep routing in `route_to_agent`, not in graph topology |
| Fact Checker drops everything and the user sees empty answers | Medium | Define the outcomes: unsupported segments removed, none left gives an `empty` block with the reason in the trace; test each |
| LLM claim-support judge is unreliable | Medium | Judge tier differs from the generator; deterministic lexical fallback; mutation suite reports a detection rate rather than asserting one |
| Gold is shaped by what retrieval finds | Medium | Written from PDF text search only; method recorded; Azim approves; frozen before any arm runs |
| Gold effort: 19 answerable questions, 4 are contradiction questions needing passages from several papers | Medium | Draft in batches; Azim reviews; quality over speed |
| The result is null (graph adds nothing), as in the pilot | Medium to high | It is a valid finding. Resolution rates, empty-graph gate and the frozen protocol make a null interpretable; report it without reframing |
| Extraction is not reproducible and a live ingest costs real money | High | Ingest once, hash the result, never re-ingest between arms; resumable per document |
| Cap too small for one ingestion | Medium | Measure on one paper first; raise the cap to $10 |
| Disk: about 740 MB free; RAGAS and scipy need space | High | Azim frees about 2 GB before B2; `scipy` only if the Wilcoxon is not hand-written |
| q-single-01 cannot be answered from the corpus | Known | Amendment decision by Azim before B1 completes |
| Agent loops or hop explosion | Low to medium | Hop and token budgets plus a loop guard, each with a test |

## Definition of done

- [ ] A multi-agent request (a cross-document comparison) runs Orchestrator, Research, Graph and Fact Checker through `route_to_agent`, ends at the Composer, renders one cited `CitedSummary` in the browser, and its trace shows each hop with tokens and outcome.
- [ ] A turn that exhausts its hop or token budget still ends at the Composer with a block, not a hang or an exception.
- [ ] No agent module imports another agent module (an import-boundary test proves it).
- [ ] The Fact Checker removes a planted unsupported claim and a planted non-verbatim quote; the mutation suite records its detection rates.
- [ ] Every graph edge an agent returns resolves to a stored chunk.
- [ ] `TurnTrace` is defined in `packages/schema`, generated, validated, served, and rendered; `schema-guardian` has reviewed it.
- [ ] All 20 questions have gold files, each approved by Azim, written before any benchmark arm was run; q-single-01 is resolved by ADR.
- [ ] The corpus is ingested once with live providers; `check_corpus_parity` is clean; the ledger total is below the cap.
- [ ] The benchmark results JSON for 5 arms × 20 questions and the paired Wilcoxon statistics are committed, with the protocol stamp, and the empty-graph gate passed or the defect is documented.
- [ ] The result is reported as measured, whatever it is.
