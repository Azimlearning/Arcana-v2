# Arcana v2: founding direction (2026-10-05)

> The founding context document for this project. It records the decisions made in planning
> sessions with Azim between 2026-09-28 and 2026-10-05, before any v2 code existed. The PRD
> paraphrases this file; when the two disagree, this file records what was actually said and the
> PRD must be corrected.

---

## 1. Where v2 comes from

- **Arcana v1** (`Azimlearning/Arcana`, frozen at tag `v1.0` / `mcait-2026-camera-ready`) is the
  FYP system: GraphRAG hybrid retrieval, 21 agents on LangGraph, a 24-component typed GenUI catalog,
  645 tests. It is the system the MCAIT 2026 paper describes.
- **The MCAIT 2026 paper** ("Graph-Grounded Generative User Interfaces for Learning: Retrieval
  Structure Determines Interface Expressiveness", accepted 5 Sep 2026, EDAS #1571344896) is the FYP
  technical paper. Its central claim: the components an interface can honestly offer are those whose
  structural precondition the retrieval layer can satisfy. All three reviewers asked for empirical
  results; the paper reports only a null pilot (4 of 16 documents, Wilcoxon p = 1.0) because
  query-entity resolution rarely fired.
- **Synapse** (`Azimlearning/GenUI-Education`, v1 to v3, v4 plan in
  `Synapse-V3/docs/ENHANCED_VERSION_PLAN.md`) is a separate GenUI product for KSSM Form 4/5 science.
  It contributes techniques, not product scope.

## 2. Decisions, with who made them

| # | Decision | Source |
|---|---|---|
| 1 | **No full merge** of Synapse into Arcana. Synapse stays its own KSSM product (library, tutor, phone, Bahasa Melayu stay out of Arcana). | Assessment 2026-09-28; Azim agreed 2026-10-05 |
| 2 | **GraphRAG is the core.** Two pillars on top: **agentic AI** and **generative UI** (the adaptive dashboard folds into GenUI). **Trained models are tools** within, not a pillar. | Azim, 2026-10-05 |
| 3 | What Synapse contributes: (a) the **trained-model method**, chiefly router distillation (LLM teacher labels, small student model, confidence-gated fallback); (b) **advanced GenUI**: a typed layout spec for the adaptive dashboard, and a verified generated artifact tier. | Azim, 2026-10-05 |
| 4 | **Governed component growth** is elevated for both Synapse v4 and Arcana v2: generated → verified → cached → audited → promoted. In Arcana, repeatedly promoted artifacts crystallise into typed components, admitted only if retrieval can satisfy their precondition. | Azim, 2026-10-05 |
| 5 | **v2 is a ground-up rebuild**, with v1 as reference. Pieces such as UI components may be copied from v1 when they suit. | Azim, 2026-10-05 |
| 6 | **Stack:** same shape as v1, current versions. | Azim, interview 2026-10-05 |
| 7 | **Single user, no auth.** | Azim, interview 2026-10-05 |
| 8 | **Fewer, more advanced agents** with "super tools"; deeper, more functional, more useful. Azim will spend more development time here. | Azim, interview 2026-10-05 |
| 9 | **No user study, no public testing.** Evaluation is **automated only**: RAGAS retrieval benchmark, extraction audit, verifier mutation tests. | Azim, interview 2026-10-05 (clarifying an apparent contradiction with his 5 Oct "okay to do the test u want and use RAGAS") |
| 10 | **Build order:** P0 walking skeleton → P1 agent core with super tools → P2 GenUI catalog + adaptive dashboard → P3 trained tools → P4 verified artifacts + governed lifecycle → P5 learning/writing depth + polish. | Azim, interview 2026-10-05 |
| 11 | **LLM:** Anthropic API direct as primary, OpenRouter as fallback, with a spend cap. | Azim, interview 2026-10-05 |
| 12 | **Deploy target:** decide later; local first. | Azim, interview 2026-10-05 |
| 13 | **Subagents:** doc-keeper, test-runner, schema-guardian, cost-auditor, plus any recommended (retrieval-auditor added). | Azim, interview 2026-10-05 |
| 14 | FYP2 deadline is not a planning concern; scope change approved by the advisor; the technical paper is the MCAIT paper plus additional content. | Azim, 2026-10-05 |
| 15 | Benchmark tooling: RAGAS as a library in the repo's own eval harness, not a website or app. Non-LLM context recall/precision primary (after gold annotation); faithfulness secondary. | Recommendation accepted 2026-10-05 |

## 3. The GenUI levels (as agreed)

| Level | What the model produces | Safety mechanism | v2 role |
|---|---|---|---|
| 1 | Typed component selections with payloads from retrieved evidence | Shared schema, fail-closed validation, registry-only rendering | Default for every answer |
| 2 | A typed layout spec (which components, which panels, what order) | Same contract as level 1; layout is data, never code | Adaptive dashboard |
| 3 | A generated interactive artifact (simulation, explorable) | Declared contract checked deterministically, verifier gate that only it can pass, sandboxed iframe with scripts only, vendored libraries | Only when no component can express the answer |

The v1 invariant "the UI is data, never code" is restated for v2 as: *the wire carries data only;
generated code exists only as a verifier-minted, hash-addressed artifact rendered in a sandboxed
iframe.*

## 4. What carries over as reference (not as code by default)

From v1: the eight invariants, schema-first codegen, the four render states per component, the
`Engine` abstraction (additive, never substitutive), the eval harness (pre-registered 20 questions,
16-paper corpus manifest, ablation runner, extraction audit script), the 24-component catalog.

From Synapse: the delivery gate (a type only the verifier can mint), the sandbox and vendor rules,
the planner → contract → generator → verifier pipeline, the physics contract idea (v4 N1), mutation
testing of the verifier (v4 N2), solvability/fuzz checks (v4 N3), the lab promotion ladder (v4 N4),
router distillation and its learning-curve method (`Synapse-V3/ml/router-distill`).

## 5. Known evidence gaps inherited from v1

- The graph signal rarely fired in the pilot because query entities resolved to nodes by exact match;
  approximate matching was added after the pilot but never measured at full scale.
- Gold annotation for the 20 questions does not exist, so context recall/precision could not be
  computed.
- The extraction-quality audit was specified and scripted but never run.
- The contradiction quote is not checked verbatim against its source, and claim verification fails
  open on provider error.
- The full benchmark was blocked by an exhausted provider quota (HTTP 402).
