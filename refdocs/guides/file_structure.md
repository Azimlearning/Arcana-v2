# File Structure: Arcana v2

> The tree as of P0 task 9 (2026-10-05). Update it when a directory is added or a module's job changes. `CLAUDE.md` holds the rules; this is the map.

## Top level

| Path | What it is |
|---|---|
| `api/` | The Python backend (FastAPI, LangGraph). Importable as the top-level package `api`. |
| `web/` | The Next.js frontend. Shares source with the backend only through `packages/schema`. |
| `packages/schema/` | Wire types in TypeScript, plus the codegen that writes `api/genui/generated.py`. |
| `scripts/` | One-off tooling that is not part of the app (the vector-store spike). |
| `eval/` | Evaluation harness. Not started (P0 task 11). |
| `refdocs/` | Every project document. `STATUS.md` first. |
| `pyproject.toml`, `uv.lock` | The one Python project, at the root so `uv run uvicorn api.main:app` works. |
| `package.json`, `pnpm-workspace.yaml` | The pnpm workspace (`web`, `packages/*`); pins pnpm 9.12.3. |
| `data/` | Runtime data (SQLite, vectors, graph, uploads). Created on first run, gitignored. |

## `api/`

| Path | Job |
|---|---|
| `main.py` | App factory. Loads settings and opens stores in the startup lifespan; every error leaves as an `ErrorEnvelope`. |
| `container.py` | Builds stores, providers and retrievers for the configured mode. |
| `fakes.py` | Fake LLM mode: dispatches on request purpose to the extraction or research fake. |
| `core/` | `settings` (typed env, fails loudly), `logging`, `errors` (the error types and HTTP map), `budget` (per-turn tokens). |
| `genui/` | `generated.py` (do not edit; from the schema), `validate.py` (the fail-closed gate), `builders.py` (raw block dicts, importable only by the Composer), `stream.py` (SSE framing). |
| `llm/` | The LLM seam: `service` (fallback, cap, ledger), `ledger` (spend and the monthly cap), `pricing`, `models`, `providers/{anthropic,openrouter,fake}`, `factory`, `json_reply`. |
| `stores/` | `GraphStore`, `VectorStore`, `DocStore` abstractions; `local/` holds the NetworkX, numpy and SQLite implementations; `preflight` checks corpus parity. |
| `ingestion/` | PDF to chunks, vectors and graph: `parse`, `chunk`, `embed`, `extract`, `pipeline`, `fakes`. |
| `retrieval/` | `dense`, `sparse`, `graph`, `entities` (query entity resolution), `fusion` (RRF), `hybrid` (entry point), `arms` (the five ablation arms), `protocol` (the frozen-settings stamp). |
| `agents/` | `research` (retrieve then answer from evidence), `compose` (the Composer stub: the only place blocks are made), `graph` (the LangGraph turn graph and `run_turn`), `state`, `fakes`. |
| `routes/` | `chat` (SSE) and `ingest` (multipart upload). `/health` is in `main.py`. |
| `tests/fixtures/` | `hybrid_retrieval.pdf` and the script that regenerates it. |
| `conftest.py` | Shared fixtures: the fixture PDF, real local stores over fake providers, an `ingested` corpus. |

Tests sit beside the module they cover as `test_*.py`.

## `web/`

| Path | Job |
|---|---|
| `app/` | Next.js App Router: `layout`, `page`, `Workspace.tsx` (the shell: upload, question, answer panel). |
| `components/genui/` | `registry.tsx` (typed over the block union; the only way a block becomes UI), `CitedSummary.tsx`, `BlockStates.tsx` (loading, empty, partial, error frames). |
| `lib/` | `stream.ts` (SSE over POST, one terminal callback), `api.ts` (upload), `store.ts` (Zustand, upsert by block id). |
| `test/fixtures.ts` | Block and stream builders for tests. |

## `packages/schema/`

| Path | Job |
|---|---|
| `src/blocks.ts`, `payloads.ts`, `api.ts`, `errors.ts` | The wire types. Start every wire change here. |
| `codegen/to_python.ts` | TypeScript to Pydantic; `pnpm codegen` writes, `pnpm codegen:check` fails on drift. |

## `refdocs/`

`STATUS.md` (where we are), `arcana-v2-PRD.md` (scope and decision log), `changelog/` (`CHANGELOG.md`, `DECISIONS.md`), `plans/` and `execution/` (what and how), `guides/` (`env_setup.md`, `checklist.md`, this file), `context/`, `evidence/` (screenshots from real runs).
