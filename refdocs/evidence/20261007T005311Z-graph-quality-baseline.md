# The structure of the current graph (G1.1 baseline)

Result file: `eval/results/20261007T005311Z-graph-quality-baseline.json`. Tool: `eval/graph_quality.py`, committed at `da20ed1` with a clean tree. Stores: `data/eval-live-live`, read only; graph hash `00454fd3...c1f830` and chunk hash `20fd0ba6...cddfb` equal the pinned values of the P2 study. No model call, no network, no spend.

## What was measured

Structure only. Definitions are in the tool's docstring and in the result file's `protocol`. In short: an edge is **stated in one sentence** when one sentence of its source chunk contains both endpoint labels as whole words; a **co-mention** is a generic relation word or an edge no single sentence of its chunk states; **drawable** is stated in one sentence of at least 20 characters with labels and relation within the `GraphView` caps. Shares are over the whole graph, not over the neighbourhoods of any question (so the 34 percent below is not the 44 percent of the P2 study, which was measured on those neighbourhoods).

## Results (16 papers, 1,570 chunks)

| Measure | Value |
|---|---|
| Nodes, edges | 11,173 and 13,972 |
| Edges whose source chunk contains both endpoint labels | 9,821 (70.3 percent) |
| Edges stated in **one sentence** of that chunk | 4,830 (**34.6 percent**) |
| Edges that are co-mentions (generic word, or no sentence states them) | 9,163 (**65.6 percent**) |
| Edges a `GraphView` could draw | 4,804 (34.4 percent) |
| Nodes mentioned in one chunk only | 7,873 (70.5 percent) |
| Nodes that appear in two or more documents | 1,294 (**11.6 percent**) |
| Nodes with no edge | 2,278 (20.4 percent) |
| Labels that are very short, all digits, or sentence-like (more than 8 words) | 52, 13, 320 |
| Degree: median, mean, p99, max | 1, 2.5, 23, 477 |
| Distinct relation strings | 1,604 (the top 20 cover 49 percent of edges) |

Largest hubs: GraphRAG 477, RAG 420, Large Language Models 299, Knowledge graphs 268, Self-RAG 240, LLMs 198, LLM 177, Retrieval Augmented Generation 176, HippoRAG 170, LightRAG 167. Most common relations: authored 1,111; uses 1,099; author 1,072; evaluated on 569; authored by 426; evaluates 283. Node types: person 2,735; method 1,544; concept 673; task 449; researcher 427; dataset 371.

## What it shows

1. **Most edges are not stated.** About two thirds of the edges are not in one sentence of the chunk they came from. Some of those are real relations that span sentences (the test is deliberately strict and lexical), so 65.6 percent is an upper bound on "wrong"; it is not a measure of error.
2. **Relation names fragment.** 1,604 distinct strings; authorship alone is spelled four ways (authored, author, authored by, author of: 2,755 edges, about 20 percent of all edges). A traversal cannot treat one relationship as one thing.
3. **One concept, several nodes.** "Large Language Models", "LLMs" and "LLM" are three hubs; "Retrieval Augmented Generation" and "RAG" are two. Only 11.6 percent of nodes occur in more than one paper, so the cross-document structure the graph is meant to give is thin.
4. **Title-page metadata is a fifth of the graph.** About 3,370 nodes are people (person, researcher, author) and about 2,750 edges are authorship edges. They are real facts in the text, but they are not concept notes and they crowd a traversal.
5. **Headroom exists.** These are the weaknesses an atomic-note builder (server-checked evidence sentences, a closed relation vocabulary, deterministic cross-document merging, a `kind` for people) targets. Whether fixing them changes retrieval is what G1.5 and G1.6 measure; this record does not claim it.

## Limits

- The sentence splitter is a simple punctuation rule; PDF text with hyphenation and line breaks ("ex- perimental") and abbreviations ("et al.") can split a sentence wrongly. It is applied identically to any graph, so the comparison with another graph stays fair, but the absolute shares are approximate.
- "Stated" is lexical (the labels occur); it does not check that the sentence expresses the relation.
- It says nothing about answer quality, and it is one ingestion of one corpus.
