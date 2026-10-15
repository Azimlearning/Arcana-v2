# P5 S6: the whole system with a real model, answering from the documents (2026-10-15)

Result: `eval/results/20261015T123511Z-grounding-live.json` (rows also in `...grounding-live.rows.jsonl`); tool `eval/grounding_live.py`, whose protocol was committed before the run; a two-question smoke run (`...grounding-live-smoke.json`) preceded it. Clean tree, the baseline's stores (the 16-paper, 1,570-passage corpus), live providers: Anthropic (`claude-sonnet-5-5` for Research and the draft, `claude-haiku-4-5` as the judge). **Spend $1.026** for 47 turns (the cost review projected $0.91 expected, $1.70 high). One attempt per turn, no retry, no prompt change.

## What was run

39 chat turns (the 20 frozen questions, `q-single-01` the control the corpus cannot answer, and the 19 extension questions) through the real graph and roster, then 8 `write` turns on fixed topics (Studio and the Fact Checker's draft checks). Measured without a model judge: verbatim quotes, citation precision and gold recall under the frozen 30 percent shingle rule, answer rate, and what the Fact Checker removed.

## Results

| Measure | Result |
|---|---|
| Answerable questions answered (terminal block `ready`) | **38 of 38** |
| The control (`q-single-01`, no answer in the corpus) | **empty, 1 of 1** (nothing invented) |
| Every citation's quote a verbatim span of its stored chunk | **100 percent** (125 of 125 re-checked in the shipped blocks) |
| Segments the Fact Checker's model judge kept | 130 of 140 (10 removed as unsupported, 7.1 percent); 0 fell to the lexical rule; 0 citations dropped |
| Quotes the model chose that passed, against replaced by the server's own sentence | 123 against 11 (8.2 percent replaced) |
| Mean citations and documents per answer | 3.3 and 2.6 |
| Citation precision (cited chunks that cover a gold passage) | **0.209** (original 19: 0.212; extension 19: 0.205) |
| Gold recall (gold passages covered by the cited chunks) | **0.215** (original 19: 0.132; extension 19: 0.297) |
| Answers that cite no gold-relevant chunk | 19 of 38 |
| Write turns: draft shown after the checker | **8 of 8** (62 passages in, 62 kept, 0 unsupported, 0 reported close to their source, 0 references rebuilt) |
| Mean cost | $0.017 per question, $0.045 per write turn |

## What this says, and what it does not

- **The grounding constraint holds on a real model.** Nothing is shown that does not rest on a verbatim stored quote, a question the corpus cannot answer is refused (not answered), and the judge removed one claim in fourteen that a valid quote did not actually support. That last number is the case for the Fact Checker: without it those ten claims were shown with a real citation under them.
- **Grounded is not the same as relevant to the gold.** Half the answers cite chunks that cover none of the gold passages, and precision is 0.21. This is retrieval's ceiling showing through (Recall@10 of the fused arm is about 0.21 on the original questions and 0.52 on the extension), plus a gold set that is a floor, not a full list: a chunk can support an answer well and still cover none of the passages annotated. It is not evidence the answers are wrong, and nothing here is a model judgement of answer quality (constraint 9).
- **The Studio's writing works with a real model:** all eight drafts passed the checker whole, with references built from the stored records (no author, year or venue invented). Eight topics, one model, one run: it shows the path, not a distribution.
- **Routing:** the rules sent 29 of 39 questions to the compare plan, 9 to single and 1 to relate, so the Graph agent ran on most turns; the frozen questions that open "What is..." were not all routed single (a question that mentions papers is a comparison).

## Limits

One run, one model, 39 questions and 8 topics; no repetition (a rerun would differ); precision and recall use the frozen gold, which is incomplete; the answers' correctness and faithfulness were not model-judged, by design; the extension questions were drafted by the system's author. One `TraversalView` block was refused by the validator on live data (`data.citations.7.quote`) and not shown (fail closed); that is a known edge of graph-derived quotes and is logged, not fixed here.
