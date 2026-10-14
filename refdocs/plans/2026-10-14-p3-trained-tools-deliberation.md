# Plan: P3 trained tools, deliberated (should v2 have trained models at all?)

> Execution doc: `refdocs/execution/2026-10-14-p3-lite-rerank.md` (a skeleton, not started). ADR: D-37 (proposed).
> Status: **Draft (2026-10-14), awaiting Azim's go.** Azim asked (2026-10-14) whether a trained model has any relevance in v2, since he does not know that it helped in v1. This is the deliberation, with the evidence that exists. **Free to decide; the proposed experiment is free in money.**

## The question

P3 in the PRD is "trained tools": a distilled mode/intent router, a Re-Rank engine after RRF, and a Mastery engine, behind one `Engine` interface, each additive to a heuristic and falling back to it. Is any of that worth building in v2, given that v2's emphasis is GraphRAG as the core, agentic AI and generative UI as the pillars, and trained models as tools "within, not a pillar" (direction doc, row 2)?

## What the evidence says

**v1 never measured a benefit, because v1 never built the engines.** The v1 repository has no `engines` package: the Re-Rank and Mastery engines exist only as a specification in its PRD (FR-ENG-01 to 07), its checklist and an ADR (ADR-017) that pulled them back into graded scope. The only learning code in v1 is an SM-2 scheduler. So there is no v1 result to carry over: "does a trained engine help" is an open question in this project, not a settled one.

**What v2's own data allows us to say about a re-ranker (free, from the stored P1 benchmark, 19 answerable questions, hybrid arm):**

| | nDCG@10 |
|---|---|
| Hybrid arm, as measured | 0.208 |
| The same ten passages, re-ordered by an oracle that knows which are relevant | 0.290 |

- The most a **perfect** re-ranker could add by re-ordering the top ten is about **+0.08 nDCG@10**, and a learned one would capture a fraction of that.
- On **6 of 19 questions the top ten contain no relevant passage at all**, so re-ordering cannot help them. The binding weakness is recall (about 0.21 at ten), not ordering.
- So a re-ranker over the top ten is bounded and small. A re-ranker over a deeper candidate list (the top 50, say) is where one could matter, because it can pull relevant passages from below rank ten; that is **not** in the stored results and would need a re-run (the embeddings of 19 questions, a few thousandths of a dollar).
- The graph work moved the same lever further: over the `atomic2` graph the vault arm raised the graph signal's nDCG@10 from 0.211 to 0.287 on the slice, a larger and more principled lever than a re-ranker, and it is already built.

**The three candidates, one by one:**

| Engine | What it would do | What would be needed | Verdict |
|---|---|---|---|
| Distilled router (the Synapse method) | Replace the one cheap LLM call that picks a mode or agent with a small student model | Thousands of labelled queries (teacher labels cost money), a training run | **Not worth it.** The router call costs a fraction of a cent on a single-user workspace with a $10 cap; the saving is nil and the training data does not exist. It would be built for the sake of the method, not the product. |
| Mastery engine (learned recall model) | Predict recall per concept from review history | Review history; one user, a few events | **Not worth training.** The learner layer's decayed-belief rule is built and sound. If review *scheduling* is wanted, adopt a published scheduler (FSRS with its default parameters) as a deterministic engine: no training data, no training. |
| Re-Rank engine | Re-order the fused list with a model that reads query and passage together | A pretrained cross-encoder (not trained by us), a candidate depth of 30 to 50, an evaluation on the 19 questions | **The only candidate with a plausible, measurable benefit**, and the cheapest to evaluate honestly. |

## The risk that is Azim's to weigh

The original FYP proposal has a **graded Objective 03, "Trained ML Models"** (v1 PRD §12A and ADR-017: "pulled back into graded scope to match Objective 03"). The v2 direction doc records that the scope change was approved by the advisor, but I cannot see that Objective 03 was removed. If it still stands, dropping P3 entirely is an assessment risk, not a technical one. The smallest honest way to keep it is one engine, evaluated against its heuristic, with the fallback verified: exactly P3's own exit criterion ("each engine evaluated against its heuristic; fallback verified").

## Recommendation: P3-lite, one measured experiment

1. **Build one engine**, the Re-Rank engine, behind the `Engine` interface (constraint 6: additive; absent or failing, RRF order runs). Use a **pretrained cross-encoder** (a MiniLM-class model, run locally): no training run, no API spend, and the claim stays honest ("a trained model, evaluated").
2. **Evaluate it** as a new arm on the same 19 questions at candidate depths 10, 30 and 50, with the paired test already in `eval/stats.py`, **against the RRF order and against the vault arm**. The protocol is written before the run (constraint 9). The result is reported whichever way it falls: a re-ranker that does not help is a finding, and it answers Azim's question with data.
3. **Do not build** the distilled router or a trained Mastery engine. If review scheduling is wanted later, adopt FSRS defaults as a deterministic engine.
4. Cost: about $0.001 of embeddings for the deeper candidate lists (to be confirmed before the run, per the standing rule); a dependency to decide (an ONNX runtime or `sentence-transformers`; the heavier the dependency, the weaker the case, so ONNX first).

## Out of scope, with reasons

- Training any model ourselves: no labelled data worth the name, and a model trained on a few thousand LLM-judged labels measures the judge, not relevance (v1's own risk R-11).
- Fine-tuning the embedding model: a different project.

## Risks and unknowns

| Risk | Impact | Confidence |
|---|---|---|
| The re-ranker does not beat RRF on 19 questions | Low: it is a result | High: the oracle ceiling is small |
| 19 questions cannot distinguish a small gain from noise | Medium | High: descriptive reporting only, as in every look so far |
| A heavy dependency (torch) for a small benefit | Medium | Medium: choose ONNX first, and stop if the footprint is large |
| Objective 03 still graded and one engine is judged too little | Medium | Unknown: Azim to confirm what the objective requires |

## Definition of done (if approved)

- `api/engines/` has the `Engine` interface and the re-rank engine; absent or failing, the heuristic order is returned (a test).
- The protocol is written before the run; the result is committed with the paired test, and says plainly whether the engine helped.
- D-37 is confirmed or reversed by that result.
