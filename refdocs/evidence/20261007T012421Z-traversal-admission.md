# What the graph signal followed on the 20 frozen questions (P2c T3)

Result file: `eval/results/20261007T012421Z-traversal-admission.json`. Tool: `eval/traversal_admission.py`, run at commit `88d9246` with a clean tree on the pinned stores (`data/eval-live-live`, read only; graph hash `00454fd3...c1f830` and chunk hash `20fd0ba6...cddfb` equal the pinned values). No model call, no network call, no spend: the Graph agent's traversal reads the graph and chunk stores only.

## What was measured

For each of the 20 questions: the concepts it resolved to (the seeds), the edges followed one hop from them, how many the `TraversalView` would show (the ones that led to a returned passage, within the caps), the ten passages the graph signal returns and how each was reached, and whether the component's precondition holds. Availability and behaviour of the graph signal; **not a quality score**, and it says nothing about questions unlike these 20.

## Results

| Measure | Value |
|---|---|
| Questions admitted a `TraversalView` | **20 of 20** (no refusal) |
| Seeds per question | 3 to 10 (median 5.5); 111 in all, **41 approximate matches (37 percent)** |
| Edges followed per question | 16 to 755 (median about 66) |
| Steps the view would show per question | 5 to 54 (median 16); the rest are counted, not shown |
| Passages reached (200 in all) by **a seed's own mention** | **174 (87 percent)** |
| Passages reached only through a neighbour concept | 26 (13 percent) |
| Passages reached because an edge was extracted from them without mentioning the seed | **0** |

Typical seeds, from the questions: "hybrid retrieval", "dense vectors", "BM25", "Knowledge graphs", but also "corpus", "evidence", "concepts", "text", "Findings", "Retrieval", "RAG", "OpenAI". The control `q-single-01` ("What is Reciprocal Rank Fusion ...", which the corpus cannot answer) is admitted too: its seeds are "retrieval system", "calibration", "PageRank score", "Mean Reciprocal Rank at K", "Embedding-fusion".

## What it shows

1. **Most of what the graph signal returns is chunks that mention a concept the question resolved to.** In the top ten, 87 percent of the passages are reached because they mention a resolved concept, and 13 percent through a neighbour concept's own mention. **The zero for "an edge alone" is structural and says nothing about whether edges matter:** on this graph every edge's source chunk is also in the chunk list of both of its endpoint nodes (extraction writes the node mentions and the edge from the same chunk), so an edge-only route cannot occur. Edges do influence the result in one way: when many chunks tie at the top score, **edge support breaks the tie** (`api/retrieval/graph.py`), and the retrieval auditor's recomputation without that key changed 31 of the 200 slots (15.5 percent), in 17 of the 20 questions (a figure from the auditor's read-only analysis, not a result file). So: resolution and node quality decide most of which passages appear, and edge support decides among many ties. "Resolution and node quality decide most of it" is plausible but was not tested against a run with edges removed.
2. **The view is available everywhere, including where it should not impress.** It is admitted on all 20 questions, including the control that the corpus cannot answer. That is honest (it shows the search followed junk concepts), but a reader could take a full diagram as evidence of an answer. The Composer admits by structure, not by quality; the view says it shows the route and not what the documents state. Recorded as a known limitation; a "the search found no strong concept" note is a possible follow-up, not built.
3. **Hubs follow hundreds of edges.** Up to 755 edges are followed on one question; showing only the edges that led to returned passages (5 to 54 per question) keeps the view within its caps, and the count of the rest is stated.

## Limits

- One ingestion of one corpus, 20 questions, of which one is a control.
- "Reached" is the graph signal's own top ten (the retriever's `TOP_K`), not the fused top ten the answer uses; the view shows the graph signal's route, which is a part of the answer's evidence, not all of it.
- The seeds' match kind comes from the resolver (exact versus approximate); no judgement of whether a seed is a good concept was made here.
