# Plan: P5, the final evidence (what the project will have measured and shown, and in what order)

> Execution doc: `refdocs/execution/2026-10-14-p5-final-evidence.md`. ADR: none yet (decisions arise per run). Scope source: PRD §6 P5, constraint 9 (the evaluation protocol is fixed before runs), D-06 (automated evaluation only, no user study).
> Status: **Draft (2026-10-14).** Started on Azim's "proceed" with P5 as the next phase (2026-10-14). Planning and the free parts are free; **every paid run needs Azim's confirmation of the amount first, and the cap has to be raised in `.env`, which only he can do.**

## Why this exists

P0 to P4 built the system. What a final-year project is judged on is what it **shows**: results that can be defended, with their limits stated. Today the evidence is scattered across looks, probes and reviews, one measurement is missing at the scale the project's own hypothesis points to (GraphRAG gains with corpus size), and the model-judged metric (RAGAS) is deliberately not installed yet. P5 turns that into a fixed, reproducible evidence set.

## What's already covered (no work needed)

| Evidence | Where | State |
|---|---|---|
| Retrieval ablation, five arms, 19 answerable questions, 16 papers, paired tests | `eval/results/20261006T093813Z-benchmark*.json`, D-26 | Done (hybrid minus flat inconclusive; descriptive) |
| The scale check: the graph signal helps the hybrid more as the corpus grows (-0.022 at 285 passages, +0.039 at 1,570) | Look 3, `refdocs/evidence/20261007T131202Z-m2-look3-scale.md` | Done on the free-form graph |
| Graph builder and the vault arm on the 3-paper slice (`atomic2`, `vault-1`) | Looks 2 and 4 | Done on the slice only |
| Component admission rates and the bound | P2 (`eval/bound.py`, `refdocs/evidence/20261006T184643Z-bound.md`) | Done |
| Fact-check and GenUI registration mutation suites | `eval/mutation_factcheck.py`, P2 | Done |
| Lab mutation suite (120 planted defects, four families) and two independent reviews | `eval/lab_mutations.py`, D-36 amendment | Done |
| Graph quality (structural) | `eval/graph_quality.py` | Done |

## Scope

**In (the evidence set, E1 to E7):**

- **E1. The scale result for the new graph.** The full 16-paper `atomic2` build, then the vault arm and the frozen arms over it, on the same 19 questions, through the existing compare tool and protocol (D-35: amendments before the run). This is the measurement the Mark 2 results point to and Azim's scale hypothesis asks for. **Paid: about $3 to $6.50.**
- **E2. The model-judged metrics.** Install RAGAS at the very end (standing instruction), run faithfulness, context precision and context recall as **secondary** metrics only (constraint 9: model-judged scores are never primary), on a bounded subset. **Paid: a judge model; the amount is to be projected by `cost-auditor` first.**
- **E3. The link audit.** Azim reads the two 100-item samples (g1-3 and `atomic2`), kind hidden; the key is applied afterwards, and the precision of stated and co-mention links is reported with its sample size. **Free; needs Azim's time.**
- **E4. P3-lite**, if approved (see its deliberation): one re-rank engine against its heuristic. **Free in money (about $0.001).**
- **E5. A learning-feature descriptive section**: what the quiz and the mastery colouring do on the real vault (counts, item quality measured by the leak count and the wrong-answer rules), **with no user study** (D-06). **Free.**
- **E6. The VerifiedLab section**: the mutation suite's rate, the review findings and what they changed, the four labs and the corpus's support for each (the `GET /labs` list is itself a constraint-7 demonstration). **Free.**
- **E7. The limits chapter, written from the ledger**: every `Noted, not changed` and every `ASSUMED:` that is still open, in one place.

**Out, with reasons:** a user study (D-06); training any model (see the P3 deliberation); a live deployment (Q-07); new components beyond what the evidence needs; anything that would change a frozen arm.

## Approach

- **Protocol before runs.** For each paid run the execution doc has a protocol paragraph (arms, metrics, the headline pairs named in advance, what counts as an improvement, the cost ceiling), committed before the run. Results are reported as measured, descriptive only (19 questions, one build per graph; no significance claims beyond the paired test the harness already runs).
- **Order by dependence and by money.** Free work first (E3 waits for Azim; E5, E6 and E7 can be drafted now); then E4 (cents); then E1 (the largest spend) once the cap is raised; E2 last (RAGAS at the end, and its cost depends on the model chosen).
- **One ledger.** Every number that goes in a chapter cites its result file and commit; `STATUS.md`'s verification table stays the index.

## Cost estimate

| Item | Estimate | Basis | Needs |
|---|---|---|---|
| E1 full `atomic2` build, then the compare | $3 to $6.50, plus about $0.01 for embeddings | The slice cost $0.8928 for 285 passages (about $0.0031 each); 1,570 passages scale to about $4.9, with a 25 percent margin each way | The cap raised; Azim's confirmation of the ceiling; a clean tree; run from the repo root |
| E2 RAGAS on a subset | $1 to $3 (unmeasured guess) | 19 questions by 3 metrics, a mid-tier judge | `cost-auditor` projection and Azim's confirmation first |
| E4 deeper candidate lists | about $0.001 | 19 question embeddings, a few times | Confirmation (tiny) |
| Everything else | $0 | Fakes or local computation | n/a |

The October cap has about $1.54 left; **E1 needs the cap raised (Azim: "okay with increasing budget limit where needed"; the edit is his, in `.env`) or the 2026-11-01 reset.**

## Risks and unknowns

| Risk | Impact | Confidence / mitigation |
|---|---|---|
| The full-corpus `atomic2` result is no better than the free-form graph at scale | Medium: a weaker headline | High: reported as measured; the vault and graph builder are still the contribution, the limits chapter says so |
| One build per graph, no temperature control: a rebuild would differ | Medium | Known; stated; a second build is an option if budget allows, not assumed |
| 19 questions: a small gain is indistinguishable from noise | Medium | High: descriptive only |
| The link audit is not read | Medium: no precision figure for edges | Azim's time; the sample is ready |
| A paid run at a dirty tree or from another directory | Low | The tool refuses; the ceiling and the ledger path are preconditions |

## Definition of done

- E1 to E7 each have a committed result or an explicit, reasoned "not done" with the cost or the person it waits on.
- Every claim in the write-up traces to a result file and a commit; the limits chapter lists every open `ASSUMED:` and `Noted, not changed`.
- The standing rules held: no key in the repo, no paid run without confirmation, no frozen arm changed, no unlogged decision.
