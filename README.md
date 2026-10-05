# Arcana v2

Graph-grounded generative UI for learning. **GraphRAG is the core**; agentic AI and generative UI
are the two pillars built on it; trained models are tools that serve those pillars.

Final Year Project, Universiti Teknologi PETRONAS: *Arcana: A GraphRAG-Powered Multi-Agent Research
and Learning Intelligence Platform*. Fakhrul Azim Bin Ahmed Mardzukie.

**Status:** scaffolded 2026-10-05. Docs and plans exist; no application code yet. See
[`refdocs/STATUS.md`](refdocs/STATUS.md).

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
- **Agents:** a small set of advanced agents with powerful typed tools (research, graph, fact
  checking, tutoring, writing, lab building) that call each other within budgets.
- **Generative UI:** answers arrive as typed components (cited summaries, comparison grids,
  contradiction alerts, concept maps), arranged by an adaptive dashboard layout spec, and, only when
  no component can express the answer, as a verified, sandboxed interactive artifact. The techniques
  for the last two come from Synapse
  ([Azimlearning/GenUI-Education](https://github.com/Azimlearning/GenUI-Education)).
- **Governed component lifecycle:** generated, verified, cached, audited, promoted. A component joins
  the vocabulary on evidence, and only when retrieval can satisfy what it asserts.
- **Evaluation first:** a gold-annotated retrieval benchmark with RAGAS, a knowledge-graph extraction
  audit, and verifier mutation testing. Automated only; no user study.

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
uv run uvicorn api.main:app --reload   # API, fakes by default
pnpm --filter web dev                  # web app
uv run python eval/run_ablation.py     # retrieval benchmark (costs money in live mode)
```

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
