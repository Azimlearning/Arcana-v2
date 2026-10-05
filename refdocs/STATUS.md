# Arcana v2: Build Status

> **Read this first to know where we are.** Updated at the end of every build session. Phases and scope come from `refdocs/arcana-v2-PRD.md` §6. Don't reorder phases without updating this file and saying why (CLAUDE.md "keep docs current").

**Build philosophy:** walking skeleton first. One PDF, one chunk, one embedding, one hybrid call, one `CitedSummary`, one streamed block, one rendered component, end to end, before building the second of anything. Evidence is measured, never asserted.

**Right now (2026-10-06):** P0 tasks 1 to 9 are built and verified on fakes, and task 11's eval harness is built and tested on v1's real 16-paper corpus in fake mode. No paid call has ever been made. Two things block the rest of P0: **task 10** (real providers behind the cap) waits for Azim's Anthropic and OpenRouter keys, and **task 11's Verify** is not fully met until RAGAS is installed (it needs about 94 packages and the development drive is nearly full). Decided: monthly cap $5 and reuse of v1's questions and manifest (D-21). The execution doc is `refdocs/execution/2026-10-05-p0-walking-skeleton.md`; its **Reality** notes say where the build diverged from the plan.

---

## Phase checklist

| Phase | Scope | Status |
|---|---|---|
| P0 | Walking skeleton + eval harness | 🔶 Tasks 1 to 9 done on fakes; task 11 built, RAGAS metrics pending install; task 10 (live providers) not started |
| P1 | Agent core with super tools; first full graph-vs-flat benchmark | ⬜ Not started |
| P2 | GenUI catalog (level 1) + adaptive dashboard (level 2 LayoutSpec) | ⬜ Not started |
| P3 | Trained tools: router distillation, Re-Rank, Mastery (optional) | ⬜ Not started |
| P4 | VerifiedLab (level 3) + governed lifecycle | ⬜ Not started |
| P5 | Learning/writing depth, final eval runs, report evidence | ⬜ Not started |

Status vocabulary: use these exactly, and never round up:
- ⬜ **Not started**
- 🔶 **In progress**: say precisely what works and what doesn't
- ✅ **Done**: built *and* verified. If it compiles but was never run, it is not done.
- ⛔ **Blocked**: name the blocker and who/what unblocks it

---

## P0: Walking skeleton + eval harness (current phase)

| Item | Approach | Status |
|---|---|---|
| Monorepo + toolchain | pnpm workspace (`web`, `packages/schema`) + uv project at the repo root; Python 3.13 (D-18) | ✅ |
| Wire schema + codegen | `UIBlock` (`CitedSummary`), `BlockMeta`, error envelope, SSE events; TS to Pydantic; strict models; drift check (D-19) | ✅ |
| Core + LLM seam | Settings, logging, error envelope, token budget, spend ledger, Anthropic primary and OpenRouter fallback | 🔶 Verified against fakes, constructed SDK errors and mocked HTTP only. No live provider call has been made; OpenRouter model ids and the embedding price are assumed |
| Stores | `GraphStore` (NetworkX), `VectorStore` (exact numpy, D-17), `DocStore` (SQLite); persistence round trip tested | ✅ |
| Ingestion | PDF to chunks (1,200 / 200), embeddings, schema-free extraction, one pass | 🔶 Verified on one 3-page fixture with fake embeddings and a fake extractor; live embeddings and real extraction not run |
| Hybrid retrieval | Dense + BM25 + graph, RRF k = 60, per-signal toggles, deterministic entity resolution; scoring frozen (D-20) | 🔶 Behaviour verified by tests on the fixture. Retrieval quality on a real corpus is unmeasured; the harness requirements from the audit are not built yet |
| One agent to one block | Research agent, Composer stub, fail-closed validator, SSE | 🔶 Verified end to end with a fake LLM. A real model's answers have never been validated |
| Web | Shell, stream consumer, registry, `CitedSummary` with all states | ✅ Verified in a real browser, including a mid-stream connection reset and an absent API |
| Eval harness | Question set + manifest (D-21), gold format, five-arm runner, Recall@10 and nDCG@10, RAGAS non-LLM metrics | 🔶 Built and tested; ran on the real corpus in fake mode. The two RAGAS metrics are `null` until RAGAS is installed. Gold is smoke only (2 questions); benchmark gold is P1 |

---

## Verification ledger

What has actually been run, not what has been written. A row here needs a real command and a real result.

| Date | What was verified | How | Result |
|---|---|---|---|
| 2026-10-05 | Toolchain installs and runs (task 1) | `test-runner`: `pnpm install --frozen-lockfile`, `uv sync --frozen`, `uv run python -c "import fastapi, langgraph, networkx"`, `pnpm -r build`, `pnpm -r typecheck`, `pnpm -r lint`, `pnpm -r test` | All exit 0; Next.js 16.3.8 builds |
| 2026-10-05 | Codegen drift check (task 2) | `pnpm codegen:check` clean; renamed `order` to `position` in `blocks.ts` without regenerating; reverted | Exit 0, exit 1, exit 0 |
| 2026-10-05 | Wire models fail closed | Reproduced that `extra='forbid'` alone accepted `"1"`, `True`, `1.0` for an int; after `strict=True`, `pytest api/genui/test_generated.py` | The three are rejected; unknown fields rejected |
| 2026-10-05 | Vector store choice (Q-02) | `scripts/vector_store_spike.py`, 2,000 random 3,072-dim vectors, 20 cosine top-10 queries, 7 candidates, Windows, Python 3.13.14 | Table in ADR D-17: numpy, faiss, lancedb, sqlite-vec exact; chromadb 0.745 and usearch 0.665 recall; hnswlib does not install |
| 2026-10-05 | Backend suite | `uv run pytest api` twice, `uv run ruff check api scripts`, `uv run pyright api`, run by me after the disk was freed | 269 passed both runs; ruff clean; pyright 0 errors |
| 2026-10-05 | Retrieval arms (task 7) | `pytest api/retrieval`: one test per arm, call-count spies for disabled signals, hand-computed RRF, failing retrievers; `retrieval-auditor` review | Pass; audit fixes applied and re-tested |
| 2026-10-05 | API server (task 8) | `uvicorn api.main:app` in fake mode; `curl` for `/health`, upload, chat | `/health` 200; upload `ready` with 4 chunks; chat streamed loading, ready, done; `/health` 200 again on port 8765 after the last change |
| 2026-10-05 | Web unit and component tests (task 9) | `pnpm --filter web test` (`test-runner` final run) | 5 files, 51 tests pass; typecheck, lint and build pass |
| 2026-10-06 | Eval harness tests (task 11) | `uv run pytest` (api plus `eval/tests`), `uv run ruff check api eval scripts`, `uv run pyright api eval`, run by me, then independently by `test-runner` (twice, no order leakage), which also ran codegen, typecheck, lint and the 51 web tests | 307 passed; ruff clean; pyright 0 errors; all JavaScript checks pass |
| 2026-10-06 | Frozen eval assets | `eval/tests/test_frozen_assets.py` pins the SHA-256 of v1's question set (body) and manifest; 20 questions (12, 4, 4); 16 papers | Pass |
| 2026-10-06 | Runner on the real corpus, fake mode | `uv run python eval/run_ablation.py --questions q-cross-01,q-single-01 --arms all --corpus-dir ../Arcana/eval/corpus` | Exit 0 in 14 s; 16 papers, 1,570 chunks, 5 arms for each question; RAGAS metrics `null` (not installed); `eval/results/*smoke-fake.json` |
| 2026-10-06 | Metric plumbing, not a bug | Gold passages matched exactly 3 chunks for q-cross-01 and 0 for q-single-01; ranks of the relevant chunks (BM25 57, 435, 723; fake dense 274, 355, 1245); positive control on q-single-02 | Zeros on q-cross-01 are real misses; q-single-02 scored recall 0.33 to 0.67 |
| 2026-10-06 | q-single-01 cannot be answered from the corpus | PyMuPDF text search of all 16 PDFs for "RRF", "rank fusion", "reciprocal" | 0, 0, 2 (both Mean Reciprocal Rank); ADR D-21 |
| 2026-10-05 | Web in a real browser (task 9) | Playwright: upload the fixture, ask a question; then a stand-in API reset the TCP connection after the loading block; then no API | Cited answer rendered with the document title, page and quote; connection-lost error alert, no skeleton left; "Could not reach the server." alert. Screenshots in `refdocs/evidence/` |

**Not verified:** the RAGAS metrics (the wrapper was written from the current docs and has not been executed); any call to Anthropic, OpenRouter or OpenAI; extraction or answer quality with a real model; retrieval on a real corpus; RAGAS; the spend cap against real costs. The independent final run of the Python checks by `test-runner` was cut short by a full disk, so the Python figures above are from my own runs (the JavaScript checks were run by `test-runner`).

---

## Known gaps

- No benchmark numbers and no benchmark gold. The harness exists; the only gold is two smoke files written by the assistant (labelled as such). Hand-annotated gold is P1 and must be written before any benchmark arm is run.
- **Question set defect (open for Azim):** q-single-01 ("What is Reciprocal Rank Fusion...") cannot be answered from the 16-paper corpus. It is handled as `unanswerable` (metrics `null`, excluded from aggregates) and was not edited; amending it (replace the question, add a paper that defines RRF, or keep it as a grounding test) is a declared amendment before the P1 benchmark (D-21).
- RAGAS is not installed (about 94 packages; the drive is nearly full). Waiting on Azim to free space, then `uv add ragas rapidfuzz` and a re-run.
- Task 10 waits for the API keys. Two assumptions to confirm then: OpenRouter's model ids, and the `text-embedding-3-large` price.
- Retrieval has only been exercised on a 4-chunk fixture with hashed bag-of-words embeddings and a fake extractor. It says nothing yet about whether the graph helps.
- The citation `quote` is a sentence chosen by the server from the cited chunk (verbatim and non-trivial, checked by the validator). A model-chosen supporting span, verified, is a P1 refinement. Chat history is accepted but unused.
- Extraction has no seed, so each ingest gives a different graph; the benchmark must treat the ingested graph as a fixed artefact.
- Request bodies are bounded by declared `Content-Length` only; a chunked body without it is not capped. Favicon is missing (cosmetic).
- Disk: the development machine's C: drive was 100 percent full during this session; `uv cache prune` freed 8.6 GiB and it was still within about 800 MB of full afterwards. Tell Azim if tests start failing with `No space left on device`.
- Evidence gaps inherited from v1 (founding context §5): no gold annotation yet, unrun extraction audit, unmeasured entity resolution (now logged per query), verbatim quote check (now enforced by the validator for the Research path).
- `.env.example` is unchanged: no new environment variable was added.
