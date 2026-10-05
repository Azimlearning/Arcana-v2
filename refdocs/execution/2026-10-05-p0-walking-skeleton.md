# Execution: P0 Walking skeleton + eval harness

> Plan: `refdocs/plans/2026-10-05-p0-walking-skeleton.md`. Tasks run top to bottom. Each task carries its own **Verify** step, and a task is not done until its Verify actually passes, not when the code compiles.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4). A stale execution doc is worse than none.
> Commands below are the ones these tasks create. Where a task names a command, that task is what makes it exist.

## Before starting

- Read `CLAUDE.md` and walk `.claude/memory/preflight.md`.
- Toolchain present: Node 24.11, uv 0.11. The machine has pnpm 10.12; `packageManager: pnpm@9.12.3` in the root `package.json` makes it fetch and run 9.12.3, so every `pnpm` command reports 9.12.3 (checked 2026-10-05; this doc previously said 9.12 was installed). Python 3.13 is used (D-18); 3.12 was never needed.
- No API keys are needed until task 10. Tasks 1 to 9 run on fakes.

## Status (updated 2026-10-06)

Tasks 1 to 9 are done: each Verify ran and passed on fakes (`ARCANA_LLM_MODE=fake`, `ARCANA_EMBED_MODE=fake`). Task 11 (eval harness) is built and tested but its Verify is **not fully met**: the two RAGAS metrics are `null` because RAGAS is not installed (it needs about 94 packages and the drive is nearly full; D-15 stays, nothing is reimplemented). Task 10 (live providers) is not started: it waits for Azim's API keys. No paid call has been made. Q-01 ($5) and Q-05 (reuse v1's set) are decided (D-21). Per-task deviations are marked **Reality** below.

---

## Task 1: Monorepo and toolchain

**Files:** `package.json`, `pnpm-workspace.yaml`, `web/package.json`, `packages/schema/package.json`, `api/pyproject.toml`, `.python-version`, root scripts.

1. Read the current Next.js, React and Tailwind install docs (context7 or the official site). Note the versions chosen in the changelog.
2. Create the pnpm workspace with `web` and `packages/schema`.
3. Create the uv project for `api` with FastAPI, uvicorn, pydantic, pydantic-settings, structlog, httpx, networkx, rank-bm25, the PDF parser, langgraph, SQLAlchemy, pytest, ruff, pyright. Try Python 3.13 first; if any dependency fails to install or import, pin 3.12 and record why (resolves Q-03 as an ADR).
4. Root scripts: `pnpm -r build`, `pnpm -r test`, `pnpm -r lint`, `pnpm -r typecheck`; backend: `uv run pytest`, `uv run ruff check api`, `uv run pyright api`.

**Verify:** `pnpm install` succeeds; `uv sync` succeeds; `uv run python -c "import fastapi, langgraph, networkx"` prints nothing and exits 0; each root script runs (an empty suite passing is fine here).

**Reality:** `pyproject.toml` is at the repo root, not `api/pyproject.toml`, so `api` is an importable top-level package and the documented commands (`uv run uvicorn api.main:app`, `uv run ruff check api`) work from the root; same layout as v1. Python 3.13 (ADR D-18). Versions chosen: Next 16.3, React 19.3, Tailwind 4.3 (`@tailwindcss/postcss`, no config file), Vitest 5, Zustand 5, TypeScript 5.9 (not 7: Next's tooling is not validated against it), ESLint 9 flat config (`next lint` was removed in Next 16), FastAPI 0.142, LangGraph 1.2, anthropic 1.11. An empty pytest exits 5, so a toolchain smoke test (`api/tests/test_smoke.py`) was added.

## Task 2: Wire schema and codegen

**Files:** `packages/schema/src/blocks.ts`, `packages/schema/src/api.ts`, `packages/schema/codegen/to_python.ts`, `api/genui/generated.py`.

1. Read v1's `packages/schema/codegen/to_python.ts`. Port it if it suits (provenance header), otherwise rewrite.
2. Define `UIBlock` with one variant, `CitedSummary`, plus `BlockMeta` (`panel`, `order`, `status`: empty | loading | partial | error) and the error envelope.
3. `pnpm codegen` writes Pydantic models; `pnpm codegen:check` exits non-zero on drift.

**Verify:** `pnpm codegen:check` exits 0. Then change one field name in `blocks.ts` without regenerating: `pnpm codegen:check` exits non-zero. Revert.

**Reality (ADR D-19):** `BlockStatus` has five values, adding `ready`. `BlockMeta` gained `error: ErrorEnvelope | null` (non-null iff status is `error`). Source files are `blocks.ts`, `payloads.ts`, `api.ts`, `errors.ts`. `CitedSummaryData` has no `summary` string (the answer is its segments). `api.ts` also defines the SSE `StreamEvent` union. Generated models are strict and forbid unknown fields; the codegen was ported from v1 with three changes (strict config, CRLF-safe `--check`, `@int` tag). `schema-guardian` reviewed after tasks 2 and 8; its findings are in the changelog.

## Task 3: Core and settings

**Files:** `api/core/settings.py`, `api/core/logging.py`, `api/core/errors.py`, `api/core/budget.py`, tests.

1. Typed settings from env; a required key that is missing raises at startup naming the variable and pointing at `refdocs/guides/env_setup.md`.
2. Structured logging; one error envelope type; a per-turn token budget object.
3. `ARCANA_LLM_MODE=fake|live` and `ARCANA_EMBED_MODE=fake|live` select fakes for tests.

**Verify:** `uv run pytest api/core` passes, including a test that startup with `ARCANA_LLM_MODE=live` and no `ANTHROPIC_API_KEY` raises an error whose message names that variable.

**Reality:** `load_settings()` raises one `ConfigError` listing every missing variable and pointing at `env_setup.md`. No new environment variable was added: the per-turn token budget is a `TokenBudget` constructor default, and the CORS origins are a constant in `api/main.py` (local dev only, D-13).

## Task 4: LLM seam with fallback, ledger and cap

**Files:** `api/llm/service.py`, `api/llm/providers/{anthropic,openrouter,fake}.py`, `api/llm/ledger.py`, tests.

1. Read the current Anthropic Python SDK docs and the OpenRouter API docs before writing the providers.
2. `complete()` tries primary, then fallback, on rate limit, timeout or provider error.
3. Every call appends to the spend ledger (SQLite table): provider, model, tokens in/out, estimated cost, purpose.
4. Before a call, refuse it if the month's ledger total plus the call's estimate exceeds `LLM_MONTHLY_CAP_USD`.

**Verify:** `uv run pytest api/llm` passes: fake primary raising → fallback used; a ledger row per call; a call over the cap refused before the provider is invoked.

**Reality:** The ledger is `api/llm/ledger.py` with its own `spend_ledger` table in the shared SQLite file; it is not part of `DocStore` (task 5 therefore has `documents`, `chunks`, `turns` only). `reserve()` then `settle()` guards against concurrent calls overshooting the cap; failed attempts are recorded at $0 with status `failed`. A refusal from the model (`stop_reason: refusal`) counts as a provider failure so the fallback runs. Embeddings (task 6) use the same ledger. Providers were written against the anthropic 1.x SDK reference and OpenRouter's chat-completions docs, and tested with constructed SDK errors and `respx`; no real call was made. Prices are first-party Anthropic rates; OpenRouter ids and the embedding price are `ASSUMED:` (DECISIONS items 4 and 5).

## Task 5: Storage abstractions and the vector-store spike

**Files:** `api/stores/{graph_store,vector_store,doc_store}.py`, `api/stores/local/*.py`, tests, `refdocs/changelog/DECISIONS.md`.

1. Spike: for each candidate local vector store, insert 2,000 random 3,072-dim vectors and run 20 cosine top-10 queries on this machine; record install success, time, and on-disk persistence. Pick one; write the ADR resolving Q-02.
2. `GraphStore` ABC (upsert node/edge, expand, shortest path, communities) with a NetworkX implementation persisted to the data directory. Edges store the source chunk id.
3. `VectorStore` ABC with the chosen local implementation.
4. `DocStore` on SQLite via SQLAlchemy: documents, chunks, turns, ledger.

**Verify:** `uv run pytest api/stores` passes, including a persistence test: write, close, reopen, read back the same graph and vectors. The ADR exists in DECISIONS.md and Q-02 is removed from the ASSUMED list.

**Reality:** The spike (`scripts/vector_store_spike.py`, seven candidates) chose an exact numpy store (ADR D-17). The `VectorStore` ABC gained `ids()` (corpus parity checks). `Node` gained `chunk_ids` (every chunk that mentions the entity), added after the retrieval audit: edges alone only reach chunks that contain a relation, which would have handicapped the graph arm. `GraphStore.delete_document(doc_id, chunk_ids)` takes the chunk ids explicitly so the abstraction does not depend on the chunk-id format. `api/stores/preflight.py` (`check_corpus_parity`) was added: chunk ids, vector ids and graph references must agree before any benchmark.

## Task 6: Ingestion

**Files:** `api/ingestion/{parse,chunk,embed,extract,pipeline}.py`, a small fixture PDF in `api/tests/fixtures/`, tests.

1. Parse PDF to text with page numbers; chunk at 1,200 characters with 200 overlap.
2. Embed (fake in tests); extract entities and relations with one schema-free LLM call per chunk (fake in tests), canonicalising entity names.
3. Write chunks, vectors and graph in one pass; each edge records its chunk id.

**Verify:** `uv run pytest api/ingestion` passes: the fixture PDF yields the expected chunk count, every chunk has a vector, the graph has nodes, and every edge's chunk id resolves to a stored chunk.

**Reality:** Files are `parse`, `chunk`, `embed`, `extract`, `pipeline` plus `types` and `fakes`. The fixture is `api/tests/fixtures/hybrid_retrieval.pdf` (3 pages, 4 chunks), regenerated by `make_fixture_pdf.py`. Extraction is genuinely schema-free (v1 restricted entity types and relation names); a malformed model reply costs that chunk its graph contribution only, but a provider outage or spend-cap refusal fails the ingestion and removes everything stored for the document, including on cancellation. A re-ingest of the same bytes replaces the document. The ported v1 chunker starts some chunks mid-word; kept unchanged for comparability with the pilot (D-14, D-15).

## Task 7: Hybrid retrieval

**Files:** `api/retrieval/{dense,sparse,graph,fusion,hybrid,entities}.py`, tests.

1. Read v1's `api/retrieval/` for reference; port with provenance where it suits.
2. Three retrievers run concurrently; a failing retriever contributes an empty ranking (degrade, not fail).
3. RRF with k = 60; top 10 per signal and after fusion; signals toggled by a parameter, not by editing code.
4. Approximate query entity resolution (token match, capped at three candidates, scored below exact match), logging the resolution hit rate per query.

**Verify:** `uv run pytest api/retrieval` passes: one test per arm (dense, sparse, graph, flat, hybrid) shows only the enabled signals contribute; a raising retriever still returns fused results; RRF ordering matches a hand-computed example.

**Reality (ADR D-20):** Query entity resolution uses no LLM call (v1's graph retriever made one per query). Added `arms.py` (the five arms, pinned as literals in a test), `protocol.py` (`protocol_stamp()`, written into every results file), and `RetrievalResult` carrying per-signal rankings, failed signals, the resolution report and latency. `retrieval-auditor` reviewed after this task; its fixes (evidence-based tie-breaks, exact-only coverage reporting, acronym matching, one query word claimed by one approximate node, signal-name validation, ulp-safe ordering) are in. Its harness requirements are now listed under task 11.

## Task 8: One agent, one block, streamed

**Files:** `api/agents/state.py`, `api/agents/research.py`, `api/agents/graph.py`, `api/genui/{validate,stream}.py`, `api/routes/{chat,ingest}.py`, `api/main.py`, tests.

1. Read the current LangGraph docs; build a graph with the single Research node and a terminal step that emits blocks.
2. Research: hybrid retrieve, synthesise with citations mapped to chunk ids, build a `CitedSummary` payload.
3. Validator re-validates every block against the generated model and turns any violation into the error envelope with field paths (fail closed). Streamer sends validated blocks over SSE.
4. `POST /ingest` (upload) and `POST /chat` (SSE).

**Verify:** `uv run pytest api` passes, including: a malformed block is rejected with its field path; a chat request on fakes yields an SSE stream whose block validates against the schema. `uv run uvicorn api.main:app` starts and `GET /health` returns 200.

**Reality:** The terminal step is `api/agents/compose.py`, the P0 stub of the Composer. Research returns a `CitedSummary` payload; only `compose.py` may import `api.genui.builders` (a test enforces it). `run_turn` re-validates every block from plain data before it is streamed, so a block built around the validator cannot leave; a failed turn still ends with a same-id error block, then the error event, then `done`. The validator (`api/genui/validate.py`) also checks that `docTitle` and `page` match the store, that quotes are verbatim and not trivial, and rejects orphan citations. A model reply that is unusable or ungrounded is `provider_unavailable` (retryable), not `validation_failed`. Every error leaves as an `ErrorEnvelope`, including 404 and 405; a 500 carries CORS headers; bodies are bounded. Added `container.py`, `fakes.py`, `agents/fakes.py`. History is accepted but unused (single-turn Research). `schema-guardian` reviewed after this task. Verified by pytest and by running uvicorn and exercising it with curl.

## Task 9: Web skeleton

**Files:** `web/app/*`, `web/lib/stream.ts`, `web/components/genui/{registry,CitedSummary,BlockStates}.tsx`, tests.

1. Read v1's `web/lib/stream.ts` and `CitedSummary.tsx`; port with provenance if suitable.
2. A minimal shell: upload box, question box, a panel the stream renders into.
3. Registry typed so an unregistered block type fails the type check; `CitedSummary` implements empty, loading, partial and error.

**Verify:** `pnpm -r test` and `pnpm -r typecheck` pass. With the API running on fakes, `pnpm --filter web dev`, upload the fixture PDF, ask a question: a `CitedSummary` renders with a citation. Kill the API mid-stream: the error state renders.

**Reality:** Files are `lib/stream.ts`, `lib/api.ts`, `lib/store.ts`, `components/genui/{registry,CitedSummary,BlockStates}.tsx`, `app/{Workspace,page}.tsx`. v1's stream consumer parsed named SSE events; v2's server sends only `data:` lines, so the framing was rewritten (the fetch plus ReadableStream approach is kept). The client guarantees one terminal callback per turn: `done`, or an error (including a stream that closes without `done`). `Registry<B>` is typed over the block union and a `@ts-expect-error` test proves an incomplete registry fails to compile; an unregistered block type at runtime renders an error state. The Verify was run in a real browser (Playwright): upload, ask, a cited answer rendered; then the API was replaced by a stand-in that resets the TCP connection after the loading block (error state rendered, nothing left spinning), and finally with no API at all (error state rendered). Screenshots are in `refdocs/evidence/`. The dev-server console showed only a favicon 404.

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

**Reality (2026-10-06):** Built: `eval/{questions.yaml,corpus/MANIFEST.json,gold/,metrics.py,ragas_metrics.py,run_ablation.py,README.md,tests/}`. The question set and manifest are copied byte-identical from v1 (provenance header on the YAML; SHA-256 pinned by a test). Relevance is a frozen text rule (30 percent of a passage's 5-word shingles), because gold is passage text, not chunk ids. The runner ran on v1's real 16-paper corpus in fake mode (1,570 chunks, 14 seconds) and wrote five arms for each question with Recall@10, nDCG@10, ranking length, latency and the graph resolution report. **Not met:** the two RAGAS metrics are `null` with a reason until RAGAS is installed (`uv add ragas rapidfuzz`); the wrapper was written from the current docs and has not been executed. Findings: (1) **q-single-01 cannot be answered from the corpus** (no paper defines RRF; ADR D-21); its gold is `unanswerable`, its metrics `null`, and it is excluded from aggregates; (2) the all-zero scores on q-cross-01 are real misses, not a bug (the three relevant chunks rank 57, 435, 723 under BM25 and 274, 355, 1245 under fake dense); a positive control on q-single-02 scored recall 0.33 to 0.67; (3) a test caught a real bug in my metric (shingle size taken from different texts for passage and chunk). The smoke gold for q-cross-01 and q-single-02 was written by the assistant and is labelled as not the benchmark gold. The runner refuses live mode without `--allow-paid`.

**Requirements added by the task 7 retrieval audit (ADR D-20).** The harness must:
- treat any `result.failed` as an invalid question run, never as zero recall, and record `failed` per question;
- cache the query embedding per question so the dense, flat and hybrid arms see identical vectors (also saves paid calls);
- record per question and arm: ranking length, latency, `resolution_hit_rate`, the exact-only hit rate, `n_exact`, `n_approx` and whether the graph ranking was empty; report the fraction of questions with an empty graph ranking, and stop (treat it as a resolution defect, not a finding) if it exceeds about 30 percent;
- run `check_corpus_parity` before the run and refuse to run if it returns any problem;
- write `protocol_stamp()`, the extraction model and corpus and store hashes into the results JSON, and never re-ingest between arms (extraction has no seed, so the ingested graph is a fixed artefact);
- report each arm's ranking length beside Recall@10, because dense always returns ten while sparse and graph can return fewer;
- annotate gold passages as text, not chunk ids (chunk ids change if parsing changes), and tune nothing on the pre-registered questions.

---

## Wrap-up (do not skip)

The DECISIONS and file-structure items are ticked; STATUS, CHANGELOG and this doc stay open until task 10 is done and RAGAS is installed so task 11's Verify is met.

- [ ] `refdocs/STATUS.md`: phase table updated, verification ledger updated with what was actually run (current through task 11's harness; finish after task 10 and the RAGAS install)
- [ ] `refdocs/changelog/CHANGELOG.md`: session entry added (entries written for 2026-10-05 and 2026-10-06; add one per further session)
- [x] `refdocs/changelog/DECISIONS.md`: ADRs for Q-02 and Q-03 (D-17, D-18), plus D-19, D-20 and D-21, resolved `ASSUMED:` items removed
- [x] Write the file-structure doc now that a tree exists (`refdocs/guides/file_structure.md`)
- [ ] This doc updated to match what actually happened (tasks 1 to 9 and 11 recorded; add task 10 when it runs)
