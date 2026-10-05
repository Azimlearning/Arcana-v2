# Arcana v2: Sources & References

> Raw research and external dependencies. The PRD is the *decided* view; this file is the *considered* view, including things that were looked at and rejected, which is often the more useful half.
> Record a source when it's chosen, and again when it's rejected. "We already tried that and here's why it didn't fit" is the single most expensive fact to re-derive.

Last updated: 2026-10-05

---

## Founding context documents

The documents this project was scaffolded from. Kept because the PRD paraphrases them and paraphrase loses detail. Paths are relative to `FYP DOCS/` unless a repo is named.

| Document | Where | What to take from it |
|---|---|---|
| v2 founding direction | `Arcana-v2/refdocs/context/2026-10-05-v2-direction.md` | Every decision and who made it |
| Arcana v1 PRD | `Arcana/docs/arcana_prd.md` (repo `Azimlearning/Arcana`, tag `v1.0`) | Invariants (§11A.3), retrieval (§10.4), engines (§12A), catalog (§13.3), NFRs (§18), eval plan (§23) |
| Arcana v1 operating brief | `Arcana/CLAUDE.md` | The eight hard invariants, skills, subagent roster |
| Arcana v1 UI/UX plan | `Arcana/docs/uiux_plan.md` | Design tokens, 24-component catalog, four states, modes |
| Arcana v1 decisions | `Arcana/.claude/memory/DECISIONS.md` | ADR-001 to ADR-020, including the engine scope history |
| MCAIT 2026 paper | `Technical-Paper/Paper/latex/main.tex`; reviews in the private `mcait-2026-paper` repo | The bound, the settings table, the pilot result, the limitations list |
| Synapse v4 plan | `GenUI-Education/Synapse-V3/docs/ENHANCED_VERSION_PLAN.md` | N1 contract, N2 mutation testing, N3 fuzz checks, N4 promotion ladder |
| Synapse v3 architecture and rules | `GenUI-Education/Synapse-V3/docs/SYSTEM_ARCHITECTURE.md`, `Synapse-V3/CLAUDE.md` | Delivery gate, sandbox, vendor rules |
| Synapse router distillation | `GenUI-Education/Synapse-V3/ml/router-distill/` (README, `EXPERIMENT_SCHEMA.md`, `train_colab.ipynb`) | Teacher labels, student model, learning curve, confidence gating |
| Synapse v2 expression grammar | `GenUI-Education/synapse-v2/lib/expr.ts` | A restricted formula language for the physics contract |

---

## External code & libraries

Licenses are as known at scaffold time; confirm each at install (checklist: new dependency).

| Name | What it does for us | Link | License | Status |
|---|---|---|---|---|
| FastAPI | Async API, SSE | https://fastapi.tiangolo.com | MIT | Chosen (D-03) |
| LangGraph | Agent state graph | https://github.com/langchain-ai/langgraph | MIT | Chosen (D-03); current API to be read in P0 |
| Pydantic / pydantic-settings | Generated models, settings | https://docs.pydantic.dev | MIT | Chosen |
| NetworkX | Graph store implementation | https://networkx.org | BSD-3-Clause | Chosen (D-09) |
| rank-bm25 | Sparse retrieval | https://github.com/dorianbrown/rank_bm25 | Apache-2.0 | Chosen (as v1) |
| SQLAlchemy | SQLite access | https://www.sqlalchemy.org | MIT | Chosen (D-09) |
| RAGAS | Retrieval metrics | https://docs.ragas.io | Apache-2.0 | Chosen (D-15); non-LLM context metrics read 2026-10-05 |
| Next.js / React | Web app | https://nextjs.org | MIT | Chosen (D-03); versions set in P0 |
| Tailwind CSS | Styling | https://tailwindcss.com | MIT | Chosen (D-03); version set in P0 |
| Zustand | UI state | https://github.com/pmndrs/zustand | MIT | Likely (as v1) |
| ts-morph | Schema codegen | https://ts-morph.com | MIT | Likely (as v1's codegen) |
| PyMuPDF | PDF parsing | https://pymupdf.readthedocs.io | AGPL-3.0 (dual-licensed) | Candidate; the AGPL is compatible with this public repo but must be noted. Alternatives considered in P0 task 6 |
| Local vector store | Dense retrieval | n/a | n/a | Spike in P0 (Q-02) |

---

## APIs & services

| Service | Used for | Pricing model | Auth / key location | Status |
|---|---|---|---|---|
| Anthropic API | Primary LLM | Pay per token | `ANTHROPIC_API_KEY` in `.env` | Chosen (D-08) |
| OpenRouter | Fallback LLM | Pay per token | `OPENROUTER_API_KEY` in `.env` | Chosen (D-08) |
| OpenAI embeddings | `text-embedding-3-large` | Pay per token | `OPENAI_API_KEY` in `.env` | Chosen (D-14) |

Keys live in `.env` (git-ignored) and are read server-side only. Never commit a key; never expose one to a client bundle.

---

## Reference material

- The papers in the MCAIT bibliography, notes in `Technical-Paper/Research/Literature-notes/`.
- Google Research, "learning interactives" with generative UI (17 Sep 2026) and arXiv 2609.20738: vetted library and agentic solvability checks.
- arXiv 2605.09360, PDE-grounded intent verification: 39 to 40% of generated simulations run but solve the wrong physics.
- Neshaei et al., "The Missing Layer" (arXiv 2606.15902): the position that runtime GenUI cannot be verified at scale; the lifecycle (D-11) answers it.
- RAGAS docs, stable: non-LLM context precision and recall (read 2026-10-05).

---

## Considered and rejected

| Option | Why it looked good | Why it lost | Recorded in |
|---|---|---|---|
| Continue in a clone of v1 | 645 tests and 24 components on day one | Carries v1's shape by default; Azim wants a fresh perspective | D-01 |
| Full merge of Synapse into Arcana | One product, one story | Different users (KSSM pupils vs university students), different safety models, scope blow-up | Founding context, decision 1 |
| Pinecone + Firestore (v1 stores) | Proven in v1 | Cloud accounts and quotas with no multi-user need | D-09 |
| Postgres / Neo4j now | Production-grade | Need a server; no Docker on the dev machine | D-09 |
| 15+ agents (v1 bar) | Matches the original proposal | Encouraged near-duplicate agents | D-05 |
| User study | Usability evidence | Azim: not doing one | D-06 |
| Git submodules for Synapse code | Single source | Costly solo; different stacks | D-16 |
| RAGAS as a hosted app / website | A dashboard | The harness must be reproducible in the repo the paper cites | D-15 |
