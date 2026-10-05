# Execution: P0 Walking skeleton + eval harness

> Plan: `refdocs/plans/2026-10-05-p0-walking-skeleton.md`. Tasks run top to bottom. Each task carries its own **Verify** step, and a task is not done until its Verify actually passes, not when the code compiles.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4). A stale execution doc is worse than none.
> Commands below are the ones these tasks create. Where a task names a command, that task is what makes it exist.

## Before starting

- Read `CLAUDE.md` and walk `.claude/memory/preflight.md`.
- Toolchain present: Node 24, pnpm 9.12, uv (checked 2026-10-05). Python 3.13 is the system Python; uv can install 3.12.
- No API keys are needed until task 10. Tasks 1 to 9 run on fakes.
- Q-01 (spend cap) must be answered by Azim before task 10.
- v1 is at `../Arcana/` (read-only reference). Do not edit it.

---

## Task 1: Monorepo and toolchain

**Files:** `package.json`, `pnpm-workspace.yaml`, `web/package.json`, `packages/schema/package.json`, `api/pyproject.toml`, `.python-version`, root scripts.

1. Read the current Next.js, React and Tailwind install docs (context7 or the official site). Note the versions chosen in the changelog.
2. Create the pnpm workspace with `web` and `packages/schema`.
3. Create the uv project for `api` with FastAPI, uvicorn, pydantic, pydantic-settings, structlog, httpx, networkx, rank-bm25, the PDF parser, langgraph, SQLAlchemy, pytest, ruff, pyright. Try Python 3.13 first; if any dependency fails to install or import, pin 3.12 and record why (resolves Q-03 as an ADR).
4. Root scripts: `pnpm -r build`, `pnpm -r test`, `pnpm -r lint`, `pnpm -r typecheck`; backend: `uv run pytest`, `uv run ruff check api`, `uv run pyright api`.

**Verify:** `pnpm install` succeeds; `uv sync` succeeds; `uv run python -c "import fastapi, langgraph, networkx"` prints nothing and exits 0; each root script runs (an empty suite passing is fine here).

## Task 2: Wire schema and codegen

**Files:** `packages/schema/src/blocks.ts`, `packages/schema/src/api.ts`, `packages/schema/codegen/to_python.ts`, `api/genui/generated.py`.

1. Read v1's `packages/schema/codegen/to_python.ts`. Port it if it suits (provenance header), otherwise rewrite.
2. Define `UIBlock` with one variant, `CitedSummary`, plus `BlockMeta` (`panel`, `order`, `status`: empty | loading | partial | error) and the error envelope.
3. `pnpm codegen` writes Pydantic models; `pnpm codegen:check` exits non-zero on drift.

**Verify:** `pnpm codegen:check` exits 0. Then change one field name in `blocks.ts` without regenerating: `pnpm codegen:check` exits non-zero. Revert.

## Task 3: Core and settings

**Files:** `api/core/settings.py`, `api/core/logging.py`, `api/core/errors.py`, `api/core/budget.py`, tests.

1. Typed settings from env; a required key that is missing raises at startup naming the variable and pointing at `refdocs/guides/env_setup.md`.
2. Structured logging; one error envelope type; a per-turn token budget object.
3. `ARCANA_LLM_MODE=fake|live` and `ARCANA_EMBED_MODE=fake|live` select fakes for tests.

**Verify:** `uv run pytest api/core` passes, including a test that startup with `ARCANA_LLM_MODE=live` and no `ANTHROPIC_API_KEY` raises an error whose message names that variable.

## Task 4: LLM seam with fallback, ledger and cap

**Files:** `api/llm/service.py`, `api/llm/providers/{anthropic,openrouter,fake}.py`, `api/llm/ledger.py`, tests.

1. Read the current Anthropic Python SDK docs and the OpenRouter API docs before writing the providers.
2. `complete()` tries primary, then fallback, on rate limit, timeout or provider error.
3. Every call appends to the spend ledger (SQLite table): provider, model, tokens in/out, estimated cost, purpose.
4. Before a call, refuse it if the month's ledger total plus the call's estimate exceeds `LLM_MONTHLY_CAP_USD`.

**Verify:** `uv run pytest api/llm` passes: fake primary raising → fallback used; a ledger row per call; a call over the cap refused before the provider is invoked.

## Task 5: Storage abstractions and the vector-store spike

**Files:** `api/stores/{graph_store,vector_store,doc_store}.py`, `api/stores/local/*.py`, tests, `refdocs/changelog/DECISIONS.md`.

1. Spike: for each candidate local vector store, insert 2,000 random 3,072-dim vectors and run 20 cosine top-10 queries on this machine; record install success, time, and on-disk persistence. Pick one; write the ADR resolving Q-02.
2. `GraphStore` ABC (upsert node/edge, expand, shortest path, communities) with a NetworkX implementation persisted to the data directory. Edges store the source chunk id.
3. `VectorStore` ABC with the chosen local implementation.
4. `DocStore` on SQLite via SQLAlchemy: documents, chunks, turns, ledger.

**Verify:** `uv run pytest api/stores` passes, including a persistence test: write, close, reopen, read back the same graph and vectors. The ADR exists in DECISIONS.md and Q-02 is removed from the ASSUMED list.

## Task 6: Ingestion

**Files:** `api/ingestion/{parse,chunk,embed,extract,pipeline}.py`, a small fixture PDF in `api/tests/fixtures/`, tests.

1. Parse PDF to text with page numbers; chunk at 1,200 characters with 200 overlap.
2. Embed (fake in tests); extract entities and relations with one schema-free LLM call per chunk (fake in tests), canonicalising entity names.
3. Write chunks, vectors and graph in one pass; each edge records its chunk id.

**Verify:** `uv run pytest api/ingestion` passes: the fixture PDF yields the expected chunk count, every chunk has a vector, the graph has nodes, and every edge's chunk id resolves to a stored chunk.

## Task 7: Hybrid retrieval

**Files:** `api/retrieval/{dense,sparse,graph,fusion,hybrid,entities}.py`, tests.

1. Read v1's `api/retrieval/` for reference; port with provenance where it suits.
2. Three retrievers run concurrently; a failing retriever contributes an empty ranking (degrade, not fail).
3. RRF with k = 60; top 10 per signal and after fusion; signals toggled by a parameter, not by editing code.
4. Approximate query entity resolution (token match, capped at three candidates, scored below exact match), logging the resolution hit rate per query.

**Verify:** `uv run pytest api/retrieval` passes: one test per arm (dense, sparse, graph, flat, hybrid) shows only the enabled signals contribute; a raising retriever still returns fused results; RRF ordering matches a hand-computed example.

## Task 8: One agent, one block, streamed

**Files:** `api/agents/state.py`, `api/agents/research.py`, `api/agents/graph.py`, `api/genui/{validate,stream}.py`, `api/routes/{chat,ingest}.py`, `api/main.py`, tests.

1. Read the current LangGraph docs; build a graph with the single Research node and a terminal step that emits blocks.
2. Research: hybrid retrieve, synthesise with citations mapped to chunk ids, build a `CitedSummary` payload.
3. Validator re-validates every block against the generated model and turns any violation into the error envelope with field paths (fail closed). Streamer sends validated blocks over SSE.
4. `POST /ingest` (upload) and `POST /chat` (SSE).

**Verify:** `uv run pytest api` passes, including: a malformed block is rejected with its field path; a chat request on fakes yields an SSE stream whose block validates against the schema. `uv run uvicorn api.main:app` starts and `GET /health` returns 200.

## Task 9: Web skeleton

**Files:** `web/app/*`, `web/lib/stream.ts`, `web/components/genui/{registry,CitedSummary,BlockStates}.tsx`, tests.

1. Read v1's `web/lib/stream.ts` and `CitedSummary.tsx`; port with provenance if suitable.
2. A minimal shell: upload box, question box, a panel the stream renders into.
3. Registry typed so an unregistered block type fails the type check; `CitedSummary` implements empty, loading, partial and error.

**Verify:** `pnpm -r test` and `pnpm -r typecheck` pass. With the API running on fakes, `pnpm --filter web dev`, upload the fixture PDF, ask a question: a `CitedSummary` renders with a citation. Kill the API mid-stream: the error state renders.

## Task 10: Real providers behind the cap

Requires Q-01 answered and keys in `.env` (see `refdocs/guides/env_setup.md`).

1. Switch `ARCANA_LLM_MODE` and `ARCANA_EMBED_MODE` to `live`.
2. Ingest one real paper from the v1 corpus manifest; ask one cross-document question.

**Verify:** a `CitedSummary` renders from real retrieval; the ledger shows the calls with costs; the month total is below the cap.

## Task 11: Eval harness and smoke run

**Files:** `eval/questions.yaml`, `eval/corpus/MANIFEST.json`, `eval/gold/` (format + README), `eval/run_ablation.py`, `eval/metrics.py`, `eval/results/`.

1. Confirm Q-05 with Azim, then copy v1's `questions.yaml` and `MANIFEST.json` unchanged, with provenance; the question set stays as pre-registered on 9 Jun 2026.
2. Define the gold format: per question, the gold chunk texts (reference contexts) and gold document ids. Write one gold entry by hand for each of two questions.
3. Read the current RAGAS docs; compute `NonLLMContextRecall` and `NonLLMContextPrecisionWithReference`, plus Recall@10 and nDCG@10, per question per arm.
4. The runner records per-query entity-resolution hit rate and latency, and writes one JSON file per run.

**Verify:** `uv run python eval/run_ablation.py --questions q-cross-01,q-single-01 --arms all` writes a JSON with five arms × two questions, each with the four metrics, the hit rate and latency.

---

## Wrap-up (do not skip)

- [ ] `refdocs/STATUS.md`: phase table updated, verification ledger updated with what was actually run
- [ ] `refdocs/changelog/CHANGELOG.md`: session entry added
- [ ] `refdocs/changelog/DECISIONS.md`: ADRs for Q-02 and Q-03, any resolved `ASSUMED:`
- [ ] Write the file-structure doc now that a tree exists (STATUS known gap)
- [ ] This doc updated to match what actually happened
