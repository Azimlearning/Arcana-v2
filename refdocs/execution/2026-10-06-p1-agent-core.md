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

**Reality (done 2026-10-06):** The tools live in `api/agents/research.py` itself, not a separate `tools/research_tools.py`; two small functions did not justify a package. `compare_documents` takes one hybrid retrieval and pools it with every signal's deeper ranking, then fills up to 8 passages round-robin, every document's best before any second-best, rather than issuing one retrieval per document: the same cost, and no per-document query to invent. The prompt groups passages by document and passage numbers follow the prompt order. Cites are `{"passage": n, "quote": "..."}`; bare integers are still accepted (server quote). A quote is kept only if it is a whitespace-normalised verbatim span of the cited chunk of at least 20 characters (the validator's own minimum), else the server's best-matching sentence replaces it. A comparison that cites one document when several were available returns `partial` with the note "comparison cites one document". Verified by `api/agents/test_research.py` (11 tests, a stubbed two-paper corpus rather than a second PDF) and the full suite (380 passed, ruff and pyright clean). The live-model quote rate (`quotes_model` vs `quotes_server` in the step stats) is not measured until Track B.

### Task A6: Graph agent

**Files:** `api/agents/graph_agent.py`, `api/agents/tools/graph_tools.py`, tests.

1. `find_path(a, b)` resolves two entities (the P0 resolver), returns the shortest path with the edge and chunk behind each hop.
2. `neighborhood(entity, hops)` returns the entity's edges and the chunks that evidence them.

**Verify:** `uv run pytest api/agents` passes: a path on a handmade graph is the expected one; every edge in every result has a chunk id that resolves in the DocStore; an unresolvable entity gives an explicit empty result with the resolution report, not an exception.

**Reality (done 2026-10-06):** One module, `api/agents/graph_agent.py` (tools included, as in A5). `TurnContext` gained an optional `graph: GraphStore`, which `chat.py` fills from the container; the default roster is now Orchestrator, Graph, Research. Path search is **not** `GraphStore.shortest_path`: a test showed it can pick a route through an edge whose chunk no longer exists while an equally short grounded route exists, so the agent searches breadth-first over grounded edges (sorted, direction ignored, deterministic) using only `GraphStore.edges()`. Entities come from the P0 resolver (exact before approximate). Two entities give a path, a path-less pair or one entity gives a one-hop neighbourhood (hops clamped to 2, at most 12 edges), nothing resolved gives `mode: "none"` with the resolution counts and a `partial` step. Research reads `chunk_ids` from `ctx.results["graph"]` (at most 3, placed first) rather than importing the agent. `api/agents/test_graph_agent.py` (20 tests); full suite 400 passed, ruff and pyright clean. Not yet seen on a real extracted graph: the fixture graph is handmade, and real node ids depend on the live extractor (Track B).

### Task A7: Fact Checker and its mutation tests

**Files:** `api/agents/fact_checker.py`, `api/agents/tools/check_tools.py`, `eval/mutation_factcheck.py`, tests.

1. `check_claims(answer)`: for each segment, (a) every citation quote is verbatim in its chunk (deterministic), and (b) the cited chunks support the claim, judged by a model from a different tier than the generator, with a deterministic lexical-overlap fallback when the judge is absent or fails.
2. Fail closed: unsupported segments are removed; none left gives an `empty` block and the reason in the trace; a checker failure never lets an unchecked answer through.
3. A small mutation suite plants known defects into valid answers (an invented claim, a non-verbatim quote, a citation to the wrong chunk) and records the detection rate per defect type.

**Verify:** `uv run pytest api/agents eval/tests` passes; the mutation suite detects every planted non-verbatim quote and wrong-chunk citation (deterministic checks) and writes its measured detection rate for invented claims to a JSON file (reported, not asserted); a checker that raises yields no answer, not an unchecked one.

**Reality (done 2026-10-06):** One module, `api/agents/fact_checker.py`, split into a pure core (`screen_answer`, `Screened.finalize`: no model, no I/O) and a thin async layer (`_judge`, `check_claims`, the agent). The deterministic check drops any citation whose chunk is missing, whose document differs, or whose quote is not a verbatim span of at least 20 characters; a segment left with no citation is removed. Support: one judge call (purpose `check`, tier `light`, the generator being `standard`) gives a verdict per segment; a segment with no usable verdict, or every segment if the call fails or the reply is unusable, falls to a lexical rule (content-word overlap of at least 0.4, a judgement, `SUPPORT_OVERLAP`). A verdict is decisive in both directions; the lexical rule never overrules one. Fake mode has no judge (`fake_check_responder` returns `{}`), so the lexical rule decides in fake runs.

**Fail closed is enforced in the Composer, not by the checker's good behaviour.** With `fact_checker` on the roster, `compose_block` shows only the checker's answer: a checker that was never run, failed or was refused gives an error block (`budget_exhausted` for a refusal), never the unchecked Research answer. Without it on the roster behaviour is as in P0. The default plans now end in `fact_checker` (`INTENT_PLANS`), and the orchestrator test says the checker runs after Research. Nothing surviving gives an `empty` block with the note "no supported claims" on the trace step. Consequence found in testing: if a cited chunk vanishes between retrieval and checking, the checker drops the answer and the block is `empty`, not `error`; the validator's error path is still reachable only without a checker, so `test_agents.py` builds that case with a checker-less roster.

**Mutation suite** (`eval/mutation_factcheck.py`, `eval/tests/test_mutation_factcheck.py`, results in `eval/results/mutation-factcheck.json`): 50 seeded cases from the 16-paper corpus, parsed and chunked only (no ingestion, no model, no cost). Measured: clean answers kept 50/50; non-verbatim quote, wrong chunk, wrong document each 50/50 (asserted in the tests); invented claim from another paper 49/50, from another chunk of the same paper 48/50; **a negated claim 0/50**. The negation row is deliberate: a "not" adds only a stopword, so a word-overlap rule cannot see it. That is the lexical fallback's known blind spot and the reason the judge exists; it means the lexical rule alone is not evidence that an answer is faithful. The model judge is **not** measured here (it costs money and is not reproducible); measuring it is a Track B option once the cap is raised. The invented claims are real corpus sentences, not model hallucinations, so those two rates are likely optimistic.

Not covered: the real judge's behaviour; the quote-verbatim rate of a live generator.

### Task A8: Trace persistence, endpoint and web panel

**Files:** `api/stores/local/sqlite_doc.py` (a new `turn_traces` table, not a column on `turns`), `api/stores/doc_store.py`, `api/routes/trace.py`, `web/components/TracePanel.tsx`, `web/lib/store.ts`, tests.

1. Persist the trace per turn. SQLite `create_all` does not alter an existing table, so use a new table rather than a new column.
2. `GET /turns/{turnId}/trace` returns a validated `TurnTrace`; unknown id is a `not_found` envelope.
3. A collapsible trace panel lists each hop with agent, status, tokens and time.

**Verify:** `uv run pytest api` passes (the endpoint round-trips a trace and rejects an unknown id); `pnpm -r test` passes a component test for the panel; `pnpm -r typecheck` passes.

**Reality (code done 2026-10-06; schema-guardian result recorded in the changelog):** Files differ from the list above: the store change is in `api/stores/doc_store.py` (`record_trace`, `get_trace`, JSON text keyed by turn id, so the store does not depend on wire types) and `api/stores/local/sqlite_doc.py` (table `turn_traces`, no foreign key to `turns` since the two rows are written independently; `_upsert` now takes the key column). The route is `api/routes/trace.py`; the component is `web/components/TracePanel.tsx` (not under `genui/`: it is a workspace panel, not a block); `fetchTrace` is in `web/lib/api.ts`, not the store, because the panel keeps its own load state and the trace is not part of the answer state. Recording happens in the `/chat` stream's `finally` block (also on client disconnect) and maps the last block streamed to the outcome: ready or partial is `answered`, empty is `empty`, anything else `error`. The endpoint validates the stored text again with `TurnTrace.model_validate_json` before returning it; a damaged row is a 500 envelope with no detail, never a half-formed trace. An id over 64 characters or unknown is a `not_found` envelope. The trace contains no question text (a test searches the body for the question's words); notes are the reason codes the framework writes. The panel loads only when first opened, writes status in words ("not run (limit reached)" for a refused hop), is mounted with `key={turnId}` so a new turn resets it, and is offered only when the turn ended normally (not when the connection died, since the server may have no trace then). A bug found by the component test: an effect that set its own loading state also listed that state as a dependency, so its cleanup discarded the response; fixed with a ref recording that the request was made. Verified: `uv run pytest` 441 passed; `pnpm --filter web test` 62 passed (51 before); `pnpm -r typecheck`, `pnpm -r lint`, `pnpm codegen:check`, `pnpm --filter web build` all exit 0. Not yet verified in a real browser (A9).

### Task A9: A multi-agent request, end to end on fakes

**Files:** `api/test_api.py`, `web/app/Workspace.test.tsx`, execution doc.

1. A cross-document comparison question runs Orchestrator, Research, Graph and Fact Checker through `route_to_agent`, ends at the Composer, and streams one `CitedSummary`; the trace shows every hop.
2. Run the real server and the web app in a browser (as in P0 task 9): ask the question, see the answer with citations from more than one document, open the trace panel.

**Verify:** `uv run pytest` and `pnpm -r test` pass; in the browser, the answer renders and the trace lists at least four hops; then force a hop budget of one and confirm the turn still ends with a block.

**Reality (done 2026-10-06):** Done in a real browser on two real corpus papers (the survey of RAG and HybridRAG, 117 and 56 chunks, ingested through the real API with fake LLM and fake embeddings). Two things were changed to make the Verify true, both recorded in D-22's amendment. (1) The comparison plan did not include the Graph agent; it now is `graph, research, fact_checker`, and `compare_documents` pools the graph's evidence chunks. (2) The first browser run cited **one** paper: the fake research responder cited the first two passages, which the document-grouped prompt puts in the same paper, and the trace correctly showed "comparison cites one document" (the A5 safety net working). The fake now cites the first passage of each distinct document when several appear, as a real comparison would. After that: the answer cited both papers and the trace listed `orchestrator, graph, research, fact checker`, all completed, 2,322 tokens in the orchestrator step (inclusive). The one-hop run used a scratch launcher outside the repo that sets `TurnLimits(max_hops=1)` on the real app: the turn ended with the error block "The turn used its hop budget." and the trace showed orchestrator completed and the other three hops "not run (limit reached)". The same case is in `api/test_api.py`. Screenshots: `refdocs/evidence/p1-a9-comparison-two-papers-trace.png`, `refdocs/evidence/p1-a9-one-hop-budget-trace.png`. Not verified: any of this with a real model, where answers, quotes, routing and the judge behave differently.

---

## Track B: gold, live corpus, benchmark (needs Azim)

### Task B1: Gold annotation for all 20 questions

**Files:** `eval/gold/q-*.yaml`, `eval/gold/README.md`, `refdocs/changelog/DECISIONS.md`.

1. Draft passages for the 19 answerable questions by keyword search of the PDF text (as done for the two smoke files), verbatim, with document and page. Never look at retrieval output. Record the method in the gold README.
2. Decide q-single-01 (replace the question, add a paper that defines RRF, or keep it as a "should find nothing" grounding test) and record it as an amendment ADR; if the question or manifest changes, update the pinned hashes in the same commit.
3. Azim reviews each file; a file becomes `status: benchmark` only after his approval.

**Verify:** `uv run pytest eval/tests` passes, including a new test that every passage of every `benchmark` file is verbatim in its paper's page text and that all 20 files exist; the ADR and the approval are in the changelog; this is complete before any benchmark arm is run.

**Reality (drafted 2026-10-06; approval pending):** All 19 answerable questions have draft gold (4 to 7 passages each, 109 in total, 1 to 7 papers per question) in `eval/gold/q-*.yaml`; `q-single-01` remains `unanswerable`. Method (recorded in the gold README): the PDFs' text per page from the pipeline's own parser, phrase and keyword search per question, passages copied verbatim, retrieval output never consulted. The two smoke files (q-cross-01, q-single-02) were replaced by benchmark drafts. Status deviates from the plan's wording: files are `status: benchmark` with `approved_by: null` rather than becoming `benchmark` only on approval, and the safety the plan wanted is enforced in code instead: `eval/run_ablation.py` refuses a live run against gold that is not approved. New: `eval/verify_gold.py` (every passage verbatim on its stated page, and covered by at least one chunk under the relevance rule; 0 problems on all files, and it caught two of my own copying errors, dropped PDF hyphenation) and tests for it and for the guard. Three questions are only partly answerable from the corpus and are flagged **review** in the README: q-single-04 (BM25's scoring formula is never given), q-cross-08 (only Self-RAG treats citation accuracy), q-contra-01 (no paper compares chunk sizes head to head). Not done: Azim's approval of each file, the q-single-01 amendment, pinning the approved files' hashes (after approval, with the frozen-asset test).

### Task B2: Live providers and prerequisites (also closes P0 task 10 and the RAGAS gap)

Requires: keys in `.env`, cap decided, disk freed.

1. Confirm the `ASSUMED:` items: OpenRouter model ids (a request per tier), the embedding price (OpenAI pricing page).
2. Install RAGAS and `rapidfuzz` (`uv add ragas rapidfuzz`), and `scipy` if the Wilcoxon is not hand-written.
3. Ingest **one** real paper with live providers; compare measured cost per chunk with the estimate and extrapolate to the corpus.

**Verify:** a `CitedSummary` renders from real retrieval; the ledger shows the calls with costs and the month total is below the cap; the measured cost per chunk is recorded in the changelog and the full-run estimate is updated.

**Reality (B2 part 1, 2026-10-06, live):** Azim put the keys in `.env` (Anthropic, OpenRouter, OpenAI, cap $10). Done with real providers, about $0.27 of the $10 spent: **(a) probe**: a few-cent call through every route. Anthropic echoes the dated id `claude-haiku-4-5-20251001` for the alias `claude-haiku-4-5` (the audit's prediction), and the D-23 pricing fix booked it at the Haiku rate ($0.000034 for 14 in and 4 out, exactly $1 and $5 per million). `claude-sonnet-5-5` works. OpenRouter's public model list confirms the assumed ids and the price table (Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 4.5 $1/$5) and Haiku through OpenRouter works; **Sonnet and Opus through OpenRouter return HTTP 402** (the account lacks the credit or limit for them; not a code defect, so the fallback exists for the light tier only until Azim tops up). **The OpenAI key is rejected: HTTP 401**, so no embedding call has succeeded. **(b) live extraction of one paper** (Ragas, 35 chunks, Haiku, fake embeddings, throwaway store): $0.00311 per chunk at the 1,024-token limit but 3 of 35 chunks truncated mid-JSON; at 2,048 tokens 1 of 35 failed and the cost is $0.00356 per chunk, projecting to about $5.6 for the corpus (ADR D-25). **(c) three real chat turns** over that paper (real routing rules, Research on Sonnet, Fact Checker judge on Haiku; queries embedded with the fake embedder to match the stored fake vectors): all `ready`; the model's supporting quotes were verbatim 9 of 9 times (server fallback never needed); the judge removed 1 of 4 segments on the relationship question; each turn cost $0.007 to $0.015. Two findings: the comparison rule matched "compared" in a question about a single paper (routing rules are crude), and capping `compare_documents` at two passages per paper gave Research only 2 passages on a one-paper corpus; the cap now fills the limit round-robin (test added). **Not done:** the one-paper ingestion with real embeddings, a rendered `CitedSummary` over real vectors, the full corpus. All wait on a valid OpenAI key.

### Task B3: Cost audit

Run `cost-auditor` on the live ingestion and benchmark path (per-call cost, retry storms, tiering, cap). Raise the cap if the extrapolated total is within 20 percent of it.

**Verify:** the auditor's report has no blocking finding; the cap exceeds the extrapolated total by a stated margin.

**Reality (B3 run 2026-10-06, before keys exist):** `cost-auditor` ran on the paid-call path (no network). Verdict: the reserve-and-settle mechanism is sound, and four things around it were blocking; all are fixed and tested (`api/llm/test_cost_hardening.py`, 22 new tests across the suite) and recorded as ADR D-23: (1) the ledger was per data directory, so the eval and the API each had their own cap, and deleting a data directory erased the spend; it is now `./data/ledger.db` in a live mode; (2) a dated model id echoed by the API (`claude-haiku-4-5-20251001`) would have been priced as the dearest model (Opus), about 4x over for Haiku, tripping a $10 cap at about $2.5 of real spend; calls are now priced by the requested model and dated suffixes are stripped; (3) `LLM_MONTHLY_CAP_USD` was required only for a live LLM, so live embeddings ran uncapped; now required if either mode is live; (4) one upload could spend the cap on a single file; documents over 600 passages (the largest in the corpus has 386) or whose worst-case cost exceeds the remaining cap are refused up front. Also fixed from the non-blocking list: SDK retries off, a cancelled embedding request now releases its reservation, a provider-reported cost is only a lower bound, the corpus loop stops at the first failed paper, a run with more than 5 percent of fresh chunks failing extraction is refused, and the Research call's `max_tokens` is 3000 (thinking tokens share it). **Not fixed, recorded:** `extraction_model` in the results stamp is hard-coded to Haiku rather than read from the ledger rows; there is no per-chunk extraction cache (a failed document is paid for again, about $0.35 to $0.6); the live API has no rate limit (it is a single-user tool, D-04: do not expose it); prices are still unverified (Sonnet 5.5 and Opus 5.5 rates, the OpenAI embedding price). **Cap arithmetic (auditor, from the code's prompt sizes):** per-call reservation about $0.0058; extraction at 400 output tokens per chunk about $3.9, at 600 about $5.5, at 800 about $7.1, every call at the 1,024 limit about $8.8 to $9.1; embeddings $0.06 to $0.09; ceiling for the run about $9.2. **Recommended cap: $10** (covers the expected $4.5 to $7 with a 30 to 55 percent margin); raise to $12 if the one-paper measurement gives more than $0.0055 per chunk (projected total above $8.6). Do not chat against the same ledger during the corpus ingestion. After the one-paper run (B2), read the ledger's `model` column and the cost per chunk to confirm the pricing fix against the live API's real behaviour.

**Reality (B3 part 2, 2026-10-06):** `retrieval-auditor` reviewed the benchmark protocol before any live run (no retrieval change needed; arms, fusion, gold and graph code are sound: graph, entity, fusion, hybrid and protocol code unchanged since the freeze commit, 109 passages over 19 questions, R of 3 to 9, `verify_gold` 0 problems). Five blocking findings, all fixed and tested (ADR D-24): **(1) a real bug in my statistics**: Wilcoxon ties were decided by exact float equality, so equal recall differences such as 4/7 and 6/7 differing in the last digit got different ranks; in a simulation of 20,000 question sets the p-value changed in 8,264 of them (one from 0.375 to 0.389); differences are now rounded to 12 decimals. **(2)** a result did not name its code: it now records the commit, whether the tree was dirty and which files, and a live run on an uncommitted tree is refused. **(3)** ingestion facts were lost if ingestion and the benchmark were separate invocations: they are saved to `ingestion_report.json` beside the stores and copied into every later results file, the stored documents must equal the manifest's, the chunk store is content-hashed, and `--expect-graph-sha256 / --expect-vectors-sha256 / --expect-chunks-sha256` refuse a run on stores that are not the ones ingestion made. **(4)** the freeze was checked only by pytest: `eval/frozen.py` now holds the pins (question body, manifest, approved gold, and a new hash of the entire retrieval protocol stamp), the paid runner checks them, and a test fails when any frozen retrieval constant changes. **(5)** the 19-question run is now a declared amendment (eval README, D-24, and `questions_selected` / `questions_excluded` in the results). Also fixed: the two primary metrics are Holm-corrected against each other, a statistics file carries a failed empty-graph gate and the code state, entity-resolution rates are aggregated per graph arm (a graph matching only a generic hub node would otherwise pass the empty-graph gate), versions and extraction/embedding parameters are recorded, and a structlog test-order failure (`eval/tests` before `api/retrieval`) is gone. **Not changed, recorded:** the graph tie-break across documents is a hash order (open question for Azim, D-24); the stamp still omits the slug code, parser and BM25 library versions (the last two are in the environment block); RAGAS metrics stay null. **How to run B4/B5:** commit, then one invocation `uv run python eval/run_ablation.py --allow-paid --questions <the 19 ids> --corpus-dir ../Arcana/eval/corpus --label benchmark`, or ingest first and record the printed store hashes, then pass them back with `--expect-*`.

**Reality (B2 part 2 and B4, 2026-10-06, live):** with a valid OpenAI key and OpenRouter credit all three routes work (Haiku, Sonnet and Opus through both providers; embeddings 3,072 dimensions; the embedding price booked as $0.13 per million matches the assumed one). One paper (Ragas) was ingested live first, then the other fifteen, all in `data/eval-live-live`, one paper at a time through the runner's own `ensure_corpus` (so the per-paper facts are saved in `ingestion_report.json`), stopping at the first failure. **Result:** 16 papers, 1,570 chunks, 11,173 graph nodes and 13,972 edges after merging across papers, 1,570 vectors, `check_corpus_parity` clean, stored documents equal the manifest, **15 extraction failures (0.95 percent, gate 5)**. **Cost: $5.8056** (extraction $5.7451, embeddings $0.0605), $0.00370 per chunk against the $0.0035 estimate; 1,570 extraction calls (733,713 tokens in, 1,002,271 out; mean 638 out per call against the 400 the plan assumed); 465,421 embedding tokens; 31 minutes of wall time. All spend this month including probes, two throwaway measurement extractions and five real chat turns: $6.1020 of the $10 cap. The full process, the cost of every paper, the per-call distribution and a CSV of all 1,706 ledger rows with what each was for are in `refdocs/evidence/2026-10-06-live-ingestion.md`, `eval/results/2026-10-06-live-ingestion-cost.json` and `eval/results/2026-10-06-live-ingestion-ledger.csv`, generated by the new `eval/report_ingestion.py` (it stops rather than guess if the ledger does not line up with the ingestion report). **Findings:** 13 of the 15 failures were replies that ran to the 2,048-token limit (a runaway reply, not a bad format), concentrated in the Siren hallucination survey (5 of 161 chunks, 3.1 percent, the highest of any paper; it has the longest outputs, mean 759 tokens) and in the large GraphRAG survey (2 of 386); the other two failed at a normal length. Cost per chunk varies from $0.0032 to $0.0043 with the paper's density, not its length. **The stores the benchmark must run on** (extraction has no seed, so a re-ingestion would be a different graph): graph `00454fd3afb00e63ab82f7e1f2c00a1551991707f9d91dc942830ad955c1f830`, vectors `3cd9426dca9160f6e377252fb95288a841d625258c29c39fa42e418d7d348f0e`, chunks `20fd0ba62ee5a5657d488c9916c85f856497a276c1c6f4386973bb12147cddfb`; pass them to the runner as `--expect-graph-sha256`, `--expect-vectors-sha256`, `--expect-chunks-sha256`. **Not done:** the benchmark itself (B5), which waits on one open decision (the graph arm's cross-document tie-break, D-24) and on committing, since a live run refuses an uncommitted tree.

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

**Reality, part 1 (2026-10-06, no keys needed):** `eval/stats.py` and `eval/tests/test_stats.py` are done. The Wilcoxon signed-rank test is hand-written (no scipy dependency): exact two-sided p from the permutation distribution of the tie-adjusted ranks, zero differences dropped and counted, rank-biserial effect size, Holm-adjusted p-values for the secondary pairs, hybrid versus flat as the pre-registered primary. Checked against brute-force enumeration of every sign assignment (12 random cases with ties and zeros) and the textbook Darwin data (W- 24, W+ 96, p 0.0413, the published value). A question with an invalid arm or no gold is left out of a pair, never scored as zero. The CLI reads a runner results file and writes `<run>-stats.json` carrying the protocol stamp, relevance rule, hashes and any fake-mode warning; on the fake smoke file hybrid equals flat, so it reports n=0 and no p-value. Not done: the benchmark run itself (needs the live corpus, B2 to B4) and RAGAS (deferred to the end of the project by Azim).

**Reality (B5 run, 2026-10-06):** run on a clean committed tree (`f931457`) against the stores of the one-shot ingestion, verified by `--expect-graph-sha256`, `--expect-vectors-sha256` and `--expect-chunks-sha256`, with `uv run python eval/run_ablation.py --allow-paid --questions <the 19 approved ids> --arms all --label benchmark`, then `uv run python eval/stats.py`. The runner's own checks passed: frozen question set, manifest, approved gold and protocol stamp; no invalid question-arm; empty-graph gate 0 of 19 (enforced); entity resolution mean hit rate 0.657, exact 0.47, every question with at least one exact entity. 19 query embeddings, cost $0.000062. **Results** (`eval/results/20261006T093813Z-benchmark.json`; mean over 19 questions): hybrid Recall@10 0.2123, nDCG@10 0.2080; dense 0.1917 and 0.1825; flat 0.1855 and 0.1686; graph 0.1690 and 0.1133; sparse 0.1424 and 0.1144. **The pre-registered test, hybrid versus flat** (`eval/results/20261006T093813Z-benchmark-stats.json`): Recall@10 mean difference +0.0268 (4 wins, 1 loss, 14 ties; n=5 non-zero pairs, W+ 11, W- 4, exact p 0.4375, rank-biserial r 0.47); nDCG@10 +0.0394 (7 wins, 4 losses, 8 ties; n=11, W+ 50, W- 16, p 0.1475, Holm-adjusted across the two primary metrics 0.2949, r 0.52). **Not significant.** No secondary pair is significant after Holm correction either (the smallest raw p is 0.016, sparse versus hybrid on nDCG@10, Holm 0.145). **Reading:** the direction favours the graph (hybrid best on both metrics, ahead of flat on both), but with most questions tied and a small sample the test cannot tell it from no effect, so the honest conclusion is inconclusive, not a win. Absolute recall is low for every arm (0.14 to 0.21): each question has only 4 to 7 annotated passages (3 to 9 relevant chunks) in a 1,570-chunk corpus of overlapping topics, so Recall@10 asks whether the retriever found the specific passages annotated, not whether it found good evidence. **Limitations the report must carry** (also in the eval README): 19 questions, a non-random sample; questions share gold passages and relevant chunks, so they are not independent; the gold was drafted by keyword and phrase search, which may favour lexical retrieval; the graph arm breaks ties in a hash order across papers (kept as frozen, D-24; changing it after seeing results would not be legitimate); the RAGAS context metrics are null; one ingestion, so graph quality is one draw (extraction has no seed). **Not done and not claimed:** a per-category breakdown (not pre-registered), any model-judged score, a second ingestion.

### Task B6: Wrap-up

STATUS, CHANGELOG, ADRs, this doc updated, file-structure doc updated; the plan's definition of done checked item by item.

**Reality (B6, 2026-10-06):** the plan's definition of done is checked item by item in `refdocs/plans/2026-10-06-p1-agent-core.md`: eight items met, two partly met (gold covers 19 of 20 questions with `q-single-01` unapproved and its exclusion declared; the benchmark has 19 questions and null RAGAS metrics, both declared in D-24 and the eval README), none unmet. STATUS, CHANGELOG, DECISIONS (D-22 to D-25), the PRD decision log and the plan and execution indexes are current. `refdocs/guides/file_structure.md` was not updated for the files P1 added (`api/agents/*`, `api/routes/trace.py`, `eval/frozen.py`, `eval/stats.py`, `eval/verify_gold.py`, `eval/report_ingestion.py`, `eval/mutation_factcheck.py`, `web/components/TracePanel.tsx`): listed as an open item in STATUS.
