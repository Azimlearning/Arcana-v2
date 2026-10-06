# Execution: P1 Agent core with super tools + first full benchmark

> Plan: `refdocs/plans/2026-10-06-p1-agent-core.md`. Tasks run in order within each track. A task is not done until its **Verify** passes, not when the code compiles.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4).

## Before starting

- Read `CLAUDE.md`, walk `.claude/memory/preflight.md`, read `refdocs/STATUS.md`.
- **Track A needs no keys.** It runs on fakes (`ARCANA_LLM_MODE=fake`, `ARCANA_EMBED_MODE=fake`).
- **Track B needs Azim:** API keys in his own `.env`, a raised cap (recommended $10), about 2 GB of free disk (RAGAS and possibly scipy), and his review of the gold. Track B does not start until Track A is green.
- Carried over from P0, still open: P0 task 10 (live providers) and the RAGAS install are folded into B2. The OpenRouter model ids and the embedding price are `ASSUMED:` and are confirmed there.
- v1 is at `../Arcana/` (read-only). Port with provenance headers.

---

## Track A: the agent layer (fakes only)

### Task A1: Read the docs and settle the roster

**Files:** `refdocs/changelog/DECISIONS.md`, `refdocs/arcana-v2-PRD.md`.

1. Read the current LangGraph docs for conditional edges, `Command`, `Send` and subgraphs (context7 or the official site). Note what P0's linear graph did not use.
2. Read v1's `api/agents/base.py`, `tier2/{cross_doc,graph_agent,comparator}.py`, `tier4/fact_checker.py`.
3. Write the roster ADR (resolves Q-04): built in P1 are Orchestrator, Research, Graph, Fact Checker and the Composer stub; Tutor, Writer, Lab Builder deferred with their phases. Record where routing lives (`route_to_agent`, not graph topology) and why.

**Verify:** the ADR exists with an id matching the PRD §7 row; Q-04 is removed from the `ASSUMED:` list and marked resolved in the PRD §8.

### Task A2: `TurnTrace` on the wire (schema first)

**Files:** `packages/schema/src/trace.ts`, `packages/schema/src/api.ts`, `api/genui/generated.py` (generated).

1. Define `AgentStep` (agent, hop, status, tokens, latency in ms, note) and `TurnTrace` (turn id, steps, hops used, tokens used, outcome) and the response type for `GET /turns/{turnId}/trace`. Follow preflight question 5: schema, `pnpm codegen`, `pnpm codegen:check`, validator.
2. Statuses and outcomes are closed string unions; numbers carry `/** @int */` where they are integers.

**Verify:** `pnpm codegen:check` exits 0, and exits non-zero after a field is renamed without regenerating (revert it). `uv run pytest api/genui` includes strict-model tests for `TurnTrace` (a string where an int is declared is rejected). Run `schema-guardian`.

### Task A3: Agent framework

**Files:** `api/agents/framework.py` (roster, tool spec, `route_to_agent`, budgets, trace recorder), `api/agents/state.py`, `api/agents/compose.py`, tests.

1. Port the shape of v1's `route_to_agent` and `@tool` with provenance. **Do not port the global registry:** the roster is an explicit object carried in the turn context.
2. `route_to_agent(name, query, ctx)`: charge a hop, check the hop and token budgets, refuse unknown agents, refuse a hop to an agent already on the call stack (loop guard), record a trace step, return a typed result with status `ok`, `partial` or `failed`.
3. Tools declare typed signatures; the JSON schema is generated from them and covered by tests.
4. Whatever happens (budget exhausted, agent raises, unknown agent), the turn still ends at the Composer.
5. An agent module never imports another agent module; only the framework dispatches.

**Verify:** `uv run pytest api/agents` passes, including: hop budget exhausted gives a `partial` result and a Composer block; token budget exhausted likewise; an agent that raises is a `failed` step and the turn still ends at the Composer; a hop back to an agent already on the stack is refused; an unknown agent is a `failed` step; trace steps arrive in call order with their tokens; an import-boundary test shows no agent module imports another.

### Task A4: Orchestrator

**Files:** `api/agents/orchestrator.py`, `api/agents/graph.py`, tests.

1. Read v1's `orchestrator.py` and graph for reference. Intent rules (single-document question, cross-document comparison, relationship between concepts) choose which agents run and in what order; when the rules are not confident, one LLM routing call decides (fake in tests).
2. Wire the turn graph so the Orchestrator plans, agents run through `route_to_agent`, and the Composer terminates.

**Verify:** `uv run pytest api/agents` passes a routing table test (each intent maps to its agent set), an LLM-fallback test (low rule confidence calls the routing LLM once, a confident rule never does), and a test that every path ends at the Composer.

### Task A5: Research super tools

**Files:** `api/agents/research.py`, `api/agents/tools/research_tools.py`, tests.

1. `retrieve_evidence(query)` wraps hybrid retrieval and returns passages with document and page.
2. `compare_documents(query)` retrieves per document and returns evidence grouped by document, so a cross-document answer cites several papers rather than one.
3. The model chooses the supporting quote for each citation; the server verifies it is a verbatim span of the cited chunk and falls back to the server-chosen sentence if it is not.

**Verify:** `uv run pytest api/agents` passes: a cross-document question on a two-paper fixture yields citations from both papers; a model-chosen quote that is not verbatim is replaced, never shown; a verbatim one is kept.

**Reality (done 2026-10-06):** The tools live in `api/agents/research.py` itself, not a separate `tools/research_tools.py`; two small functions did not justify a package. `compare_documents` takes one hybrid retrieval and pools it with every signal's deeper ranking, then takes up to two passages per document round-robin (cap 8), rather than issuing one retrieval per document: the same cost, and no per-document query to invent. The prompt groups passages by document and passage numbers follow the prompt order. Cites are `{"passage": n, "quote": "..."}`; bare integers are still accepted (server quote). A quote is kept only if it is a whitespace-normalised verbatim span of the cited chunk of at least 20 characters (the validator's own minimum), else the server's best-matching sentence replaces it. A comparison that cites one document when several were available returns `partial` with the note "comparison cites one document". Verified by `api/agents/test_research.py` (11 tests, a stubbed two-paper corpus rather than a second PDF) and the full suite (380 passed, ruff and pyright clean). The live-model quote rate (`quotes_model` vs `quotes_server` in the step stats) is not measured until Track B.

### Task A6: Graph agent

**Files:** `api/agents/graph_agent.py`, `api/agents/tools/graph_tools.py`, tests.

1. `find_path(a, b)` resolves two entities (the P0 resolver), returns the shortest path with the edge and chunk behind each hop.
2. `neighborhood(entity, hops)` returns the entity's edges and the chunks that evidence them.

**Verify:** `uv run pytest api/agents` passes: a path on a handmade graph is the expected one; every edge in every result has a chunk id that resolves in the DocStore; an unresolvable entity gives an explicit empty result with the resolution report, not an exception.

### Task A7: Fact Checker and its mutation tests

**Files:** `api/agents/fact_checker.py`, `api/agents/tools/check_tools.py`, `eval/mutation_factcheck.py`, tests.

1. `check_claims(answer)`: for each segment, (a) every citation quote is verbatim in its chunk (deterministic), and (b) the cited chunks support the claim, judged by a model from a different tier than the generator, with a deterministic lexical-overlap fallback when the judge is absent or fails.
2. Fail closed: unsupported segments are removed; none left gives an `empty` block and the reason in the trace; a checker failure never lets an unchecked answer through.
3. A small mutation suite plants known defects into valid answers (an invented claim, a non-verbatim quote, a citation to the wrong chunk) and records the detection rate per defect type.

**Verify:** `uv run pytest api/agents eval/tests` passes; the mutation suite detects every planted non-verbatim quote and wrong-chunk citation (deterministic checks) and writes its measured detection rate for invented claims to a JSON file (reported, not asserted); a checker that raises yields no answer, not an unchecked one.

### Task A8: Trace persistence, endpoint and web panel

**Files:** `api/stores/local/sqlite_doc.py` (a new `turn_traces` table, not a column on `turns`), `api/stores/doc_store.py`, `api/routes/trace.py`, `web/components/TracePanel.tsx`, `web/lib/store.ts`, tests.

1. Persist the trace per turn. SQLite `create_all` does not alter an existing table, so use a new table rather than a new column.
2. `GET /turns/{turnId}/trace` returns a validated `TurnTrace`; unknown id is a `not_found` envelope.
3. A collapsible trace panel lists each hop with agent, status, tokens and time.

**Verify:** `uv run pytest api` passes (the endpoint round-trips a trace and rejects an unknown id); `pnpm -r test` passes a component test for the panel; `pnpm -r typecheck` passes.

### Task A9: A multi-agent request, end to end on fakes

**Files:** `api/test_api.py`, `web/app/Workspace.test.tsx`, execution doc.

1. A cross-document comparison question runs Orchestrator, Research, Graph and Fact Checker through `route_to_agent`, ends at the Composer, and streams one `CitedSummary`; the trace shows every hop.
2. Run the real server and the web app in a browser (as in P0 task 9): ask the question, see the answer with citations from more than one document, open the trace panel.

**Verify:** `uv run pytest` and `pnpm -r test` pass; in the browser, the answer renders and the trace lists at least four hops; then force a hop budget of one and confirm the turn still ends with a block.

---

## Track B: gold, live corpus, benchmark (needs Azim)

### Task B1: Gold annotation for all 20 questions

**Files:** `eval/gold/q-*.yaml`, `eval/gold/README.md`, `refdocs/changelog/DECISIONS.md`.

1. Draft passages for the 19 answerable questions by keyword search of the PDF text (as done for the two smoke files), verbatim, with document and page. Never look at retrieval output. Record the method in the gold README.
2. Decide q-single-01 (replace the question, add a paper that defines RRF, or keep it as a "should find nothing" grounding test) and record it as an amendment ADR; if the question or manifest changes, update the pinned hashes in the same commit.
3. Azim reviews each file; a file becomes `status: benchmark` only after his approval.

**Verify:** `uv run pytest eval/tests` passes, including a new test that every passage of every `benchmark` file is verbatim in its paper's page text and that all 20 files exist; the ADR and the approval are in the changelog; this is complete before any benchmark arm is run.

### Task B2: Live providers and prerequisites (also closes P0 task 10 and the RAGAS gap)

Requires: keys in `.env`, cap decided, disk freed.

1. Confirm the `ASSUMED:` items: OpenRouter model ids (a request per tier), the embedding price (OpenAI pricing page).
2. Install RAGAS and `rapidfuzz` (`uv add ragas rapidfuzz`), and `scipy` if the Wilcoxon is not hand-written.
3. Ingest **one** real paper with live providers; compare measured cost per chunk with the estimate and extrapolate to the corpus.

**Verify:** a `CitedSummary` renders from real retrieval; the ledger shows the calls with costs and the month total is below the cap; the measured cost per chunk is recorded in the changelog and the full-run estimate is updated.

### Task B3: Cost audit

Run `cost-auditor` on the live ingestion and benchmark path (per-call cost, retry storms, tiering, cap). Raise the cap if the extrapolated total is within 20 percent of it.

**Verify:** the auditor's report has no blocking finding; the cap exceeds the extrapolated total by a stated margin.

### Task B4: Live ingestion of the corpus, once

**Files:** `eval/run_ablation.py` (as is), `data/eval-live-live/` (gitignored).

1. Run the ingestion with `--allow-paid` after `retrieval-auditor` has reviewed the protocol stamp and the freeze (D-20). Ingest each paper once; never re-ingest between arms.
2. Record per-document extraction failures and hash the graph and vectors.

**Verify:** `check_corpus_parity` returns no problems; all 16 documents are `ready`; the ledger total is below the cap; the graph and vector hashes are recorded.

### Task B5: The benchmark and the paired test

**Files:** `eval/stats.py`, `eval/tests/test_stats.py`, `eval/results/`, `eval/README.md`.

1. Write the paired Wilcoxon signed-rank test over per-question differences (hybrid vs flat on Recall@10 and nDCG@10, plus the other pairs), with n, the statistic, the p-value and an effect size; test it against a hand-computed example.
2. Run the five arms over the 20 questions with real embeddings, RAGAS metrics included. Apply the empty-graph gate (enforced at 20 questions).
3. Commit the results and the statistics. Report the numbers as measured, including a null.

**Verify:** `uv run pytest eval/tests` passes; `eval/results/` holds the results JSON and the statistics JSON with the protocol stamp, relevance rule and hashes; the gate passed or the defect is written up; no arm shows an invalid run that was scored as zero.

### Task B6: Wrap-up

STATUS, CHANGELOG, ADRs, this doc updated, file-structure doc updated; the plan's definition of done checked item by item.
