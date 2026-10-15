# Arcana v2

Graph-grounded generative UI for learning. **GraphRAG is the core**; agentic AI and generative UI
are the two pillars built on it; trained models are tools that serve those pillars.

Final Year Project, Universiti Teknologi PETRONAS: *Arcana: A GraphRAG-Powered Multi-Agent Research
and Learning Intelligence Platform*. Fakhrul Azim Bin Ahmed Mardzukie.

**Status (2026-10-15):** built and measured. Phases P0 to P5 are implemented and verified (see
[`refdocs/STATUS.md`](refdocs/STATUS.md)); the evidence, with every limit stated, is indexed in
[`refdocs/evidence/README.md`](refdocs/evidence/README.md). The headline findings are honest ones: hybrid
retrieval with the graph signal is **not shown to beat dense retrieval alone** on this corpus (38 questions, no
pair significant), the grounding constraint holds with a real model (every quote verbatim, an unanswerable
question refused), and a trained re-ranker was built, measured and not shown to help.

## Relationship to v1

v2 is a ground-up rebuild, not a continuation. Arcana v1
([Azimlearning/Arcana](https://github.com/Azimlearning/Arcana), frozen at tag `v1.0`, the system the
MCAIT 2026 paper describes) is the **reference**: its design, its lessons and its evaluation harness
inform v2. Individual pieces, for example GenUI components, are copied across only when they suit the
v2 design, and each copied file notes where it came from.

## What it does

A single user drops in their documents (papers, notes, chapters) and asks questions across them.

- **GraphRAG core:** documents become a knowledge graph plus a vector index; retrieval fuses graph
  traversal, dense and sparse signals by rank, so relations between sources are retrievable.
- **Agents:** a small set of advanced agents with typed tools (Orchestrator, Research, Graph, Fact
  Checker, Studio for learning and writing, and the Composer that alone chooses components) that call
  each other only through `route_to_agent`, within hop and token budgets.
- **Studio:** a cited, Fact Checker-checked writing draft with a bibliography built from the stored
  records (never generated); flashcards, blurting, Cornell notes and Socratic questions from the
  vault with no model call; and a review schedule from the learner's mastery.
- **Generative UI:** answers arrive as typed components (cited summaries, comparison grids, concept
  maps, search paths, drafts, study sets), admitted only when the evidence satisfies a written
  precondition, arranged by an adaptive dashboard layout spec, and, for interactive formulas, as a
  verified, sandboxed lab (a generated function that only the verifier can let through). The techniques
  for the last two come from Synapse
  ([Azimlearning/GenUI-Education](https://github.com/Azimlearning/GenUI-Education)).
- **Governed lifecycle:** a verified lab is cached, audited and promoted by use, and evicted or marked
  stale when it no longer verifies or its template, contract or generator changed.
- **Evaluation first:** a gold-annotated retrieval benchmark (20 frozen questions and a declared
  extension of 19), paired exact tests, RAGAS as a secondary metric, a link audit, mutation suites for
  every checker, and a live grounding run. Automated only; no user study.

## Requirements

- Node 20 or newer, pnpm 9.12
- Python 3.12 or 3.13 (settled in P0), uv
- API keys only for live mode: Anthropic, OpenRouter, OpenAI (embeddings). See
  [`refdocs/guides/env_setup.md`](refdocs/guides/env_setup.md).

## Setup

```bash
cp .env.example .env      # fill in values; never commit .env
uv sync                   # backend (available after P0 task 1)
pnpm install              # web + schema (available after P0 task 1)
```

## Usage

```bash
uv run uvicorn api.main:app --reload   # API, fakes by default (ARCANA_LLM_MODE=fake)
pnpm --filter web dev                  # web app on http://localhost:3000
uv run pytest -q                       # backend tests
pnpm -r test                           # web and schema tests
uv run python eval/run_ablation.py     # retrieval benchmark (costs money in live mode)
```

A live run needs `LLM_MONTHLY_CAP_USD` set to a positive number (every paid call is booked and refused
before sending if it would pass it) and the three keys; RAGAS is the optional `eval` extra
(`uv sync --extra eval`).

### A short demonstration

1. Start the API and the web app, upload a PDF, and ask a question: an answer with numbered citations,
   each a verbatim quote of a stored passage; choose **Adaptive** to see the layout the server composed.
2. In the Studio shelf choose **Write an outline**, finish the request with a topic: a cited draft with a
   bibliography you can copy as APA, IEEE or BibTeX.
3. Choose **Flashcards** (or Cornell notes, Socratic questions, Blurting), reveal a sentence and rate yourself;
   **Quiz me** for fill-in-the-blank questions checked by the server; then **Review schedule** to see what is
   due and **Learning insights** for where you stand.
4. Try **Document brief** (key points, terms and next steps for one document), **Cheat sheet** (a concept
   and its neighbours on a page, with a diagram), **Literature review**, **Abstract** and **Audio overview**
   (a cited two-voice script; read-aloud is a future enhancement, so its Listen button does nothing yet).
5. On any output choose **Open in a pane**: it opens beside the conversation, with a **Table** view you can
   sort, filter and download as CSV; drag the divider, or **Expand** to give the pane the whole centre.
6. Open **Labs** to run a verified formula lab (offered only where a stored passage states the formula),
   and **Notes** for the concept pages, graph, quiz and lint.

## Project layout

Planned; created in P0.

```
api/              FastAPI backend: core, llm, stores, ingestion, retrieval, agents, genui, engines, labs
web/              Next.js app: shell, registry, catalog components, sandbox host
packages/schema/  wire types, the single source of truth, generated into Python
eval/             questions, corpus manifest, gold set, ablation runner, audit, mutation suite
refdocs/          PRD, status, decisions, plans, execution docs, guides
```

## Documentation

| Doc | What's in it |
|---|---|
| [`refdocs/STATUS.md`](refdocs/STATUS.md) | Where the build actually is right now |
| [`refdocs/arcana-v2-PRD.md`](refdocs/arcana-v2-PRD.md) | Scope, architecture, roadmap, decision log |
| [`refdocs/context/2026-10-05-v2-direction.md`](refdocs/context/2026-10-05-v2-direction.md) | The founding decisions and who made them |
| [`refdocs/changelog/CHANGELOG.md`](refdocs/changelog/CHANGELOG.md) | Session-by-session history |
| [`refdocs/changelog/DECISIONS.md`](refdocs/changelog/DECISIONS.md) | Why things are the way they are |
| [`refdocs/guides/env_setup.md`](refdocs/guides/env_setup.md) | Every environment variable and where to get it |
| [`refdocs/guides/checklist.md`](refdocs/guides/checklist.md) | Pre-ship checklist |
| [`CLAUDE.md`](CLAUDE.md) | Operating brief for AI sessions on this repo |
