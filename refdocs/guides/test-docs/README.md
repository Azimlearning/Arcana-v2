# Test documents

Three small invented papers for the manual test guide (`../manual-testing.md`). They are not real publications.

| File | Passages | Purpose |
|---|---|---|
| `dense_retrieval_basics.pdf` | 2 | definitions and claims about dense retrieval |
| `sparse_retrieval_and_bm25.pdf` | 2 | BM25, TF-IDF, inverted index; a second, different definition of dense retrieval (for the notes lint) |
| `fusion_reranking_and_metrics.pdf` | 2 | rank fusion, rerankers and metrics; the sentences the F1@k and RankNet labs recognise |
| `optional/injection_test.pdf` | 1 | text that gives orders and carries spreadsheet and markup payloads (hostile-text checks only; not read by the corpus builder) |

- `make_test_docs.py` regenerates the PDFs (`uv run python refdocs/guides/test-docs/make_test_docs.py`).
- `build_test_corpus.py` builds a data directory in which the vault tools (quiz, flashcards, brief, cheat sheet) have claims to work from
  (`uv run python refdocs/guides/test-docs/build_test_corpus.py --out data/manual-live --allow-paid`, about $0.02).
