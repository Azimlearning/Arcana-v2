# Arcana v2: Changelog

> Mandatory session log. Add an entry after **every** session where code changed, a decision was made, or a plan was modified. Newest first. Even a one-line fix gets a one-line entry.

Entry format:
```
### YYYY-MM-DD: [short summary of session goal]
- **Changed:** what files/components were touched and why
- **Decided:** any architectural or design decisions and the reasoning
- **Deviations:** anything that differed from the plan, and why
- **Verified:** what was actually run, and the result (not "should work")
- **Known issues / next steps:** what was left open
```

Those five lines are the floor, not the ceiling. Add these when the session earns them; a debugging session in particular is unreadable without the first two:
- **Reported:** the symptom in the user's own words, before you knew the cause
- **Diagnosed:** what you found, and how you proved it (the reproduction, not the hypothesis)
- **Trade-off:** what this change costs, and who it costs it to
- **Noted, not changed:** something you found and deliberately left alone, so the next session doesn't re-investigate it

Rules that make this file worth keeping:
- **"Verified" means a command was run.** Name it and give the result. If nothing was run, write "nothing verified this session"; that is useful information.
- **Deviations are the most valuable line.** A plan that changed silently is a plan nobody will trust next time.
- **Write what you learned, not what you touched.** "Fixed the retriever" ages into nothing. "Graph traversal returned nothing because query entities matched node ids exactly" is still worth reading in six months.
- Don't rewrite history. Corrections go in a new entry that references the old one.

---

## [Unreleased]

### 2026-10-05: P0 tasks 1 to 9 (walking skeleton on fakes)
- **Changed:** Built the monorepo and everything in P0 up to the web skeleton, on fakes only (`ARCANA_LLM_MODE=fake`, `ARCANA_EMBED_MODE=fake`). `packages/schema` (wire types, a ported and hardened TS-to-Pydantic codegen); `api/core`, `api/llm` (provider seam with fallback, spend ledger, monthly cap), `api/stores` (NetworkX, exact numpy, SQLite), `api/ingestion`, `api/retrieval` (dense, BM25, graph, RRF, five ablation arms), `api/agents` (Research, a Composer stub, a LangGraph turn graph), `api/genui` (the fail-closed validator, SSE), `api/routes`, `api/main.py`; `web/` (stream client, store, typed block registry, `CitedSummary` with five states, upload and chat shell); `scripts/vector_store_spike.py`; `refdocs/guides/file_structure.md`; `refdocs/evidence/` (two screenshots). Ten files were ported from v1 with provenance headers (codegen, chunker, PDF parser, extractor, fusion, sparse, graph and hybrid retrieval, stream consumer, `CitedSummary`), each read in full and changed where v2 differs.
- **Decided:** D-17 exact numpy vector store (resolves Q-02, from a seven-candidate spike); D-18 Python 3.13 (resolves Q-03); D-19 strict wire models, five block statuses, `BlockMeta.error`, upsert by block id; D-20 graph-retrieval scoring and tie-breaks frozen before gold annotation. Q-08 resolved (current Tailwind and LangGraph docs read). New `ASSUMED:` items: OpenRouter model ids, and the `text-embedding-3-large` price.
- **Deviations:** `pyproject.toml` is at the repo root, not `api/` (the documented commands need it; same as v1). `BlockStatus` has five values, not four. The spend ledger lives in `api/llm/ledger.py`, not in `DocStore`. `Node` gained `chunk_ids` and `VectorStore` gained `ids()`. Query entity resolution uses no LLM (v1 made a call per query). Added files the doc did not list: `agents/compose.py`, `container.py`, `fakes.py`, `retrieval/{arms,protocol,entities}.py`, `stores/preflight.py`, `llm/json_reply.py`. The doc said pnpm 9.12 was installed; pnpm 10.12 is, and the `packageManager` pin makes it run 9.12.3. TypeScript is 5.9, not 7. All recorded as **Reality** notes in the execution doc.
- **Diagnosed:**
  - A fusion test failed because my premise was wrong: rank 1 in one list (1/61) does not outrank rank 10 in two lists (2/70); agreement beats a single top rank. I had also written the false claim into the fixture PDF's text; both fixed.
  - Nine backend tests failed only in the full run: `configure_logging` binds structlog to pytest's captured stderr, which is closed after that test, so later tests that log wrote to a dead stream. Proved by running the suite alone versus whole; fixed with a structlog reset after each logging test.
  - A web stream test failed for a fixture reason: `controller.error()` right after `enqueue()` discards queued chunks per the streams spec, so "keeping what arrived" could not hold. A pull-based fixture delivers each chunk before erroring, like a real drop.
  - Three reviews found real defects, all fixed. `schema-guardian` after task 2: `extra='forbid'` alone still coerced `"1"` into an int (reproduced first, then fixed with strict mode). `retrieval-auditor` after task 7: graph ties broken by a hash, free scoring constants, corpus parity, a silent signal failure. `schema-guardian` after task 8: validation was by convention (a `model_construct`'d block would have streamed), a failed turn left a stuck loading block, and 404, 405 and 500 bypassed the envelope.
- **Trade-off:** The exact numpy store holds the whole matrix in memory (about 12 KB per chunk, 614 MB at 50,000 chunks) and scans it per query; past about 50,000 chunks swap an indexed store behind `VectorStore`. Document-order tie-breaking in the graph arm favours early chunks, deliberately: it is interpretable, which a hash order is not.
- **Noted, not changed:** The ported v1 chunker starts some chunks mid-word; kept for comparability with the pilot. `rank_bm25` can give non-positive idf on very small corpora and v1's drop of scores at or below zero is kept. The Research quote is a server-chosen sentence, not a model-chosen span. History is accepted but unused. `.env.example` could not be read or edited here (the project denies it) and needed no change: no environment variable was added. Chunked request bodies are not capped. The favicon is missing.
- **Verified:** `test-runner` (separate agent, commands run): `pnpm install --frozen-lockfile`, `uv sync --frozen`, the import check, `pnpm codegen:check`, `pnpm -r typecheck`, `pnpm -r lint`, `pnpm -r build` all exit 0, and `pnpm -r test` passes 51 web tests. Me, after the disk was freed: `uv run pytest api` 269 passed on two runs, `uv run ruff check api scripts` clean, `uv run pyright api` 0 errors, uvicorn `/health` 200. The codegen drift check was exercised both ways (exit 0, exit 1 after a field rename, exit 0 after revert). In a real browser (Playwright): upload, question, cited answer rendered; a stand-in API that reset the TCP connection after the loading block gave the connection-lost error state; no API gave "Could not reach the server." **Not verified:** any call to Anthropic, OpenRouter or OpenAI, answer or extraction quality with a real model, retrieval on a real corpus. `test-runner`'s final Python run was cut off by a full disk, so the Python figures are mine.
- **Known issues / next steps:** Azim: set `LLM_MONTHLY_CAP_USD` (Q-01) for task 10, and confirm Q-05 before task 11. Rotate the two Anthropic API keys that were pasted into the chat during this session; they are not stored in the repo and nothing was written to `.env`. The C: drive was 100 percent full mid-session (`uv cache prune` freed 8.6 GiB with Azim's approval; about 800 MB free afterwards): check what else is filling it. Task 11 must build the harness requirements listed in the execution doc.

### 2026-10-05: Project scaffolded
- **Changed:** Created the project doc system: `refdocs/` (PRD, STATUS, sources, founding context, guides/, changelog/DECISIONS, plans/, execution/), `CLAUDE.md`, `README.md` (merged with the earlier one-file README), `.gitignore`, `.env.example`, `.claude/` (settings, secret-guard hook, five agents, three commands, memory/preflight). No application code yet.
- **Decided:** D-01 to D-16 (PRD §7): ground-up rebuild with v1 as reference; GraphRAG core with agentic AI and GenUI pillars, trained models as tools; same stack shape at current versions; single user, no auth; fewer, deeper agents with super tools; automated evaluation only; build order P0 to P5; Anthropic primary with OpenRouter fallback and a spend cap; local storage behind abstractions; three GenUI levels with a data-only wire; governed component lifecycle; additive engines; embeddings unchanged from v1; eval metrics; port by copying with provenance.
- **Verified:** Nothing to verify; no code exists yet. Doc checks run at scaffold time: no unfilled template tokens, docs not gitignored, secret hook fired against a planted key and a clean file.
- **Known issues / next steps:** Q-01 (spend cap) needs Azim's number before any paid call. Q-02 (vector store) and Q-03 (Python version) resolve in P0. Q-05 (reuse v1 question set and corpus) needs confirmation before gold annotation. Next session starts from `refdocs/plans/2026-10-05-p0-walking-skeleton.md`.
