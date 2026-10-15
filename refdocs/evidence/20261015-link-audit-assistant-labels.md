# Link audit of the full-corpus `atomic2` vault, labelled by the assistant (2026-10-15)

Sample: `eval/results/20261014T185317Z-m2-audit-sample.md` (100 items: 50 asserted and 50 co-mention links, fixed seed, kind hidden). Labels and summary: `eval/results/20261014T185317Z-m2-audit-assistant-labels.json`; the key was applied only after every item was labelled.

**What this is, and is not.** The protocol asked a person to read the sample. This is the assistant's reading (a model, working from each sentence alone, same model family as the extraction that made the links), done because the human reading is still outstanding. It is a **secondary, model-judged estimate**, not the human audit, and is reported as such (constraint 9: model-judged scores are never the primary metric). Rubric: *yes* the sentence supports the relation between the two concepts; *weak* related only loosely, by name containment or co-occurrence; *no* not related as shown, or a concept is spurious.

## Result

| Link kind | n | yes | weak | no | yes | yes or weak |
|---|---|---|---|---|---|---|
| Asserted (one sentence states it) | 50 | 43 | 1 | 6 | **0.86** (about 0.74 to 0.93) | 0.88 |
| Co-mention (same passage) | 50 | 29 | 16 | 5 | **0.58** (about 0.44 to 0.71) | 0.90 |

Intervals are Wilson 95 percent, for orientation only (n = 50 per kind, one labeller).

## What it shows

- **Asserted links are mostly right:** 43 of 50 supported by their sentence. The six refusals are a spurious concept (the word "context", "correct", "attention", "target") or a concept attached to the wrong subject (the Self-RAG node on sentences that describe RAG in general or GraphRAG).
- **Co-mention links are mostly loosely related, rarely wrong:** 29 yes, 16 weak (a concept that is a name-substring of the other, or two generic words in one sentence), 5 no. Used as "these are discussed together", they hold; used as "these are related", they are weaker, which is how the vault already treats them (a different link kind, shown separately).
- **Bibliography noise is the largest quality issue:** 30 of the 100 sentences are reference-list entries, not prose (20 of the 50 asserted). The relations drawn from them are true (a paper's title and its authors) but of little use in notes for learning. A filter that drops reference-list passages before link extraction is the obvious fix; it was not made, so as not to change a built, measured graph.
- **Spurious generic concepts** ("context", "attention", "tasks", "relation", "query") account for most of the "no" and "weak" labels: the extraction keeps generic words as concepts.

## Limits

One labeller, the same model family as the extraction (shared blind spots are likely); labelled from the sentence alone, with no passage context; 50 items per kind; a subjective rubric; one sample of three drawn. The human reading of this and the two earlier samples remains open and would supersede these figures.
