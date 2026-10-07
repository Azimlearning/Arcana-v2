# M2 free probes: what the Mark 1 losses were, measured before the Mark 2 design was fixed

Script: `eval/m2_probes.py` (no model call, no network, no store written). Inputs: the four replies saved during the G1 pilot (`data/g1/diag_replies.json`) and the Mark 1 slice graph (`data/g1/slice-atomic`, graph sha256 `d29a863a...b962db`, builder g1-3, 3 papers, 285 passages). Run 2026-10-07 on clean commit `f61532f`, then reproduced from the repo copy of the script with identical numbers. Cost: $0.

## Results

| Probe | Result | Reading |
|---|---|---|
| Concept labels the model proposed that occur in their own chunk (hyphen-blind, whole word) | 24 of 29 (83 percent) | The model names concepts well; most Mark 1 concept losses came from the copy-a-sentence rule, not from bad concepts |
| Proposed relations with both labels in one sentence of the chunk | 4 of 11 (36 percent) | The one-sentence evidence rule is the real limiter of relations; making the server choose the sentence would help only up to about this figure |
| Distinct asserted entity pairs in the Mark 1 slice graph | 173 (221 edges) | |
| Deterministic sentence co-mention pairs among the same 744 nodes | 674 | Free; about four times the asserted pairs |
| Passages with at least one co-mention | 184 of 285 | |
| Nodes with no asserted edge | 542 of 744 (72.8 percent) | Mark 1's thinness |
| Nodes with no link of either kind | 302 of 744 (40.6 percent) | Adding co-mentions removes about a third of the isolation |
| Most-mentioned notes (passages) | RAG 53, SELF-RAG 33, LLMs 31, reflection tokens 17, Retrieval-Augmented Generation 17, large language models 16 | Aliases are separate nodes ("RAG" and "Retrieval-Augmented Generation"; "LLMs" and "large language models"): pages must group them, and generic concepts need a spread discount |

## Limits

The first two rows rest on four chunks (29 concepts, 11 relations): a direction, not an estimate. The co-mention count uses every sentence naming two of a chunk's own nodes, with no cap on how many concepts a sentence may name and no exclusion of people or organisations, so it is an upper bound on what the registered layer (D-35) keeps. Nothing here says the new links are right: that is what the blind audit of both link kinds is for.

## What was decided from it

The registered Mark 2 design (D-35) takes the co-mention layer and concept pages first (free, measurable before any spend), a server-chosen sentence with a two-sentence window for relations, and a spread discount for concepts found everywhere. These probes were seen **before** the Mark 2 constants were set; D-35 says so and counts the Mark 2 run on the same slice as a second look.
