# P4 V1: which formulas the stored passages actually hold

Probe: `eval/lab_probe.py` over `data/m2/full-freeform-vault1` (all 16 papers, 1,570 passages). Result file: `eval/results/20261008-p4-v1-formula-probe.json`. Read-only, no model, no embedding, **free**. A passage counts when it names the method and holds a symbolic form of it (the patterns are in the file).

| Candidate | Passages | Documents | Note |
|---|---|---|---|
| Reciprocal rank fusion | **0** | 0 | not in the corpus at all (the name is not in any passage) |
| BM25 term saturation | **0** | 0 | 38 passages in 7 papers mention BM25, none states its formula |
| Cosine similarity | 1 | 1 | one passage gives a chunking distance `1 - max(cos(...), 0)`, a mangled equation |
| RankNet pairwise loss | 2 | 1 | `L = sum_i sum_j 1[r_i < r_j] log(1 + exp(s_j - s_i))`, the same paper (3a2ca3) on pages 4 and 16 |
| Pointwise BCE | 1 | 1 | `L = - sum 1[r_i = 1] log sigma(s_i) + 1[r_i != 1] log sigma(1 - s_i)`, with `sigma(x) = 1 / (1 + exp(-x))`, same paper, page 17 |
| InfoNCE loss | 2 | 1 | `min L = -log phi(t+, r+) / (phi(t+, r+) + sum phi(t+, n_i))`, with phi the cosine similarity, paper 01d82c, page 13 |
| Answer relevance score | 1 | 1 | `AR = (1/n) sum_i sim(q, q_i)`, paper 6c2476, page 3 |

## What this changes

The plan's assumption (D-36, `ASSUMED:` row 1) was that the first contracts would be retrieval-scoring formulas such as reciprocal rank fusion and BM25. **The corpus does not support that**: those two have no formula in any stored passage, so a contract citing a passage could not be written for them. The formulas the passages do hold are **loss and score functions** (RankNet, pointwise BCE, InfoNCE, the answer-relevance average). PDF extraction mangles the symbols (`s_j - s_i` appears as `sj ?si`), so each contract's source is the sentence as stored and the reference implementation is written by hand from the formula, not parsed from the text.

**Decision for V1 (still an `ASSUMED:` for Azim):** the first contract is the **RankNet pairwise loss** (a closed form of one difference, with clear properties: finite, non-negative, strictly increasing in `s_j - s_i`, equal to log 2 when the scores are equal), cited to the stored passage on page 16. The pointwise BCE and the answer-relevance average are the next contracts. Nothing is lost by this narrowing: the gate is the point, and the mutation suite does not depend on which formula is first.

## Limits

Regex patterns over mangled PDF text: a passage whose equation lost its symbols is not found, so the counts are a lower bound. The corpus is 16 retrieval papers; another corpus would give another list.
