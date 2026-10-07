# File Structure: Arcana v2

> The tree as of the end of P1 (2026-10-06). Update it when a directory is added or a module's job changes. `CLAUDE.md` holds the rules; this is the map.

## Top level

| Path | What it is |
|---|---|
| `api/` | The Python backend (FastAPI, LangGraph). Importable as the top-level package `api`. |
| `web/` | The Next.js frontend. Shares source with the backend only through `packages/schema`. |
| `packages/schema/` | Wire types in TypeScript, plus the codegen that writes `api/genui/generated.py`. |
| `scripts/` | One-off tooling that is not part of the app (the vector-store spike). |
| `eval/` | Evaluation harness: frozen question set and manifest, gold, metrics, the five-arm runner, results. See `eval/README.md`. |
| `refdocs/` | Every project document. `STATUS.md` first. |
| `pyproject.toml`, `uv.lock` | The one Python project, at the root so `uv run uvicorn api.main:app` works. |
| `package.json`, `pnpm-workspace.yaml` | The pnpm workspace (`web`, `packages/*`); pins pnpm 9.12.3. |
| `data/` | Runtime data (SQLite, vectors, graph, uploads). Created on first run, gitignored. |

## `api/`

| Path | Job |
|---|---|
| `main.py` | App factory. Loads settings and opens stores in the startup lifespan; every error leaves as an `ErrorEnvelope`. |
| `container.py` | Builds stores, providers and retrievers for the configured mode. |
| `fakes.py` | Fake LLM mode: dispatches on request purpose (extract, research, route, check) to the matching fake. |
| `core/` | `settings` (typed env, fails loudly), `logging`, `errors` (the error types and HTTP map), `budget` (per-turn tokens). |
| `genui/` | `generated.py` (do not edit; from the schema), `validate.py` (the fail-closed gate: one rule set per block type, plus `validate_layout`), `builders.py` (raw block dicts, importable only by the Composer and `templates.py`), `catalog.py` (the template record for each component: precondition, fences, placement hint, check; plus the pre-checks `graph_edges`, `alignment_grid`, `concept_path`), `layout.py` (prebuilt and adaptive `LayoutSpec`; importable only by the Composer), `templates.py` (registration with planted-defect suites, fixture store, pipeline stages), `patterns.py` (saved patterns), `alignment.py` and `text.py` (shared evidence helpers), `stream.py` (SSE framing, including the layout event). |
| `llm/` | The LLM seam: `service` (fallback, cap, ledger; prices by the requested model, D-23), `ledger` (spend and the monthly cap; one file `data/ledger.db` in a live mode), `pricing`, `models`, `providers/{anthropic,openrouter,fake}`, `factory`, `json_reply`. |
| `stores/` | `GraphStore`, `VectorStore`, `DocStore` abstractions (`DocStore` also keeps each turn's trace); `local/` holds the NetworkX, numpy and SQLite implementations; `preflight` checks corpus parity. |
| `ingestion/` | PDF to chunks, vectors and graph: `parse`, `chunk`, `embed`, `extract` (output limit 2,048 tokens, D-25), `pipeline` (per-document size and budget checks), `fakes`. |
| `retrieval/` | `traversal` (a read-only account of what the graph signal followed, with the retriever untouched), `dense`, `sparse`, `graph`, `entities` (query entity resolution), `fusion` (RRF), `hybrid` (entry point), `arms` (the five ablation arms), `protocol` (the frozen-settings stamp). |
| `agents/` | `framework` (`Roster`, `route_to_agent`: hop and token budgets, loop guard, trace steps, tool schemas), `orchestrator` (intent rules, one light-tier call when unsure), `research` (`retrieve_evidence`, `compare_documents`; model-chosen quotes verified verbatim), `graph_agent` (`find_path`, `neighborhood`; grounded edges only), `fact_checker` (quote check, judge plus lexical fallback; pure core), `roster` (the one module that imports every agent), `compose` (the Composer stub: the only place blocks are made; shows only what the Fact Checker passed), `graph` (the LangGraph turn graph and `run_turn`), `state` (`TurnContext`), `fakes`. Agents never import each other (a test enforces it). |
| `routes/` | `chat` (SSE; records each turn and its trace), `ingest` (multipart upload), `trace` (`GET /turns/{id}/trace`), `workspace` (`GET /workspace`: the prebuilt layout and the source list, no model call) and `patterns` (save, list, delete, apply as SSE, re-verify). `/health` is in `main.py`. |
| `tests/fixtures/` | `hybrid_retrieval.pdf` and the script that regenerates it. |
| `conftest.py` | Shared fixtures: the fixture PDF, real local stores over fake providers, an `ingested` corpus. |

Tests sit beside the module they cover as `test_*.py`.

## `web/`

| Path | Job |
|---|---|
| `app/` | Next.js App Router: `layout`, `page`, `Workspace.tsx` (the shell: upload, question, answer panel). |
| `components/TracePanel.tsx` | The collapsible record of what the agents did on a turn (loads when first opened; status in words). |
| `components/genui/` | `registry.tsx` (typed over the block union; the only way a block becomes UI), `CitedSummary`, `SourceList`, `GraphView` (with `graphLayout.ts`, a deterministic layout), `ComparisonGrid`, `ConceptMap`, `BlockStates.tsx` (loading, empty, partial, error frames), `ids.ts` (`safeId`, for every fragment anchor). |
| `components/shell/` | `Shell` and `Panel` (draw a `LayoutSpec`: panels, and each panel's regions in rows or columns, with animated shares), `LayoutSwitch` (Basic or Adaptive), `Studio` (the inert generator list, D-32), `SavedViews` (the outputs shelf list: each saved view with its state in words) and `SaveView` (save a view from an answer). |
| `lib/` | `stream.ts` (SSE over POST, one terminal callback; also `streamApply`), `api.ts` (upload, trace, workspace, patterns), `store.ts` (Zustand: blocks by id, layouts, layout choice, saved views), `layout.ts` (`isLayoutSpec`, `readLayout` which also reads a version 1 layout, the fallback layout, `placeBlocksByRegion`, `placeBlocks`, `flattenPlaced`). |
| `test/fixtures.ts` | Block and stream builders for tests. |

## `eval/`

| Path | Job |
|---|---|
| `questions.yaml`, `corpus/MANIFEST.json` | v1's pre-registered 20 questions and 16-paper manifest, byte-identical (D-21), pinned by hash. PDFs are not in the repo. |
| `gold/` | Hand-annotated gold passages (`q-*.yaml`) and the format and relevance rule (`README.md`). |
| `metrics.py` | Recall@10 and nDCG@10 against gold passages. |
| `ragas_metrics.py` | RAGAS non-LLM context metrics, imported lazily. |
| `run_ablation.py` | The five-arm runner; one JSON per run in `results/`. A live run checks the freeze, names its commit and refuses stores that are not the ingested ones (D-24). |
| `frozen.py` | Every pinned hash (question set, manifest, approved gold, the whole protocol stamp) and `check_frozen`; used by pytest and by the runner. |
| `stats.py` | Hand-written Wilcoxon signed-rank (exact p, Holm, rank-biserial effect size); writes `<run>-stats.json`. |
| `verify_gold.py` | Checks every gold passage is verbatim on its page and reachable by a chunk. Needs the PDFs. |
| `mutation_factcheck.py` | Plants known defects in valid answers and records how many the Fact Checker catches. |
| `graph_quality.py` | The structure of a graph with no model call (stated and co-mention edges, relation spellings, shared nodes, hubs); the baseline of the pinned graph is in `refdocs/evidence/`. |
| `traversal_admission.py` | How often a `TraversalView` is admitted and what the graph signal followed on the 20 questions (free, no model or network call). |
| `report_ingestion.py` | Writes the cost record of a live ingestion from the spend ledger (totals, per paper, per call, CSV). |
| `results/` | Committed results: the smoke run, the mutation suite, the live ingestion record, and the first benchmark with its statistics. |
| `tests/` | Metric, frozen-asset, runner, statistics, gold-verifier and report tests. |

## `packages/schema/`

| Path | Job |
|---|---|
| `src/blocks.ts`, `payloads.ts`, `api.ts`, `errors.ts`, `trace.ts` | The wire types (`trace.ts`: `TurnTrace`, `AgentStep`). Start every wire change here. |
| `codegen/to_python.ts` | TypeScript to Pydantic; `pnpm codegen` writes, `pnpm codegen:check` fails on drift. |

## `refdocs/`

`STATUS.md` (where we are), `arcana-v2-PRD.md` (scope and decision log), `changelog/` (`CHANGELOG.md`, `DECISIONS.md`), `plans/` and `execution/` (what and how), `guides/` (`env_setup.md`, `checklist.md`, this file), `context/`, `evidence/` (screenshots from real runs and the live ingestion cost record).
