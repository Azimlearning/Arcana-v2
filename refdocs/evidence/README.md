# Evidence index

> One table of every written evidence record and the result files behind it, with what it supports and its stated limit. Screenshots are named by phase and are listed at the end. A claim in the write-up cites a row here, the result file and the commit the file records. Keep this current when a record is added (P5 task F1).

| Record | Result files | Supports | Stated limit |
|---|---|---|---|
| [2026-10-06-live-ingestion.md](2026-10-06-live-ingestion.md) | `eval/results/2026-10-06-live-ingestion-cost.json`, `...-ledger.csv` | The 16-paper corpus was ingested live; the per-call cost is measured | One run; one corpus |
| P1 benchmark (recorded in `STATUS.md` and D-26) | `eval/results/20261006T093813Z-benchmark.json`, `...-benchmark-stats.json` | The five-arm ablation on 19 answerable questions: hybrid minus flat is inconclusive (descriptive, paired test) | 19 questions; one graph; RAGAS metrics null |
| [20261006T184643Z-bound.md](20261006T184643Z-bound.md) | `eval/results/20261006T184643Z-bound.json` | The component bound: which components retrieval can honestly satisfy | Study over the 20 questions |
| [20261007T005311Z-graph-quality-baseline.md](20261007T005311Z-graph-quality-baseline.md), [20261007T021458Z-g1-slice-and-baseline-v2.md](20261007T021458Z-g1-slice-and-baseline-v2.md) | `eval/results/20261007T005311Z-...`, `20261007T021458Z-...` | Structural graph quality of the free-form graph | Structural, not correctness |
| [20261007T012421Z-traversal-admission.md](20261007T012421Z-traversal-admission.md) | `eval/results/20261007T012421Z-traversal-admission.json` | TraversalView admission on the 20 questions | One corpus |
| [20261007-g1-pilot.md](20261007-g1-pilot.md), [20261007T051315Z-g1-subset.md](20261007T051315Z-g1-subset.md) | `eval/results/20261007T051315Z-g1-subset*.json`, `20261007T051342Z-audit-*` | The atomic-note graph (G1): retrieval about equal from a graph a third the size; the registered gate failed one clause by 0.0056 | 3 papers; 19 questions |
| [20261007-m2-brainstorm-probes.md](20261007-m2-brainstorm-probes.md) | (inline) | The free probes behind the Mark 2 plan | Probes |
| [20261007T060911Z-m2-look2.md](20261007T060911Z-m2-look2.md) | `eval/results/20261007T060911Z-m2-look2.json`, `20261007T060948Z-m2-audit-sample.*` | The vault is a stronger graph signal over the same nodes (0.141 to 0.227) but does not improve the hybrid | 3 papers; gate clause 3 uninformative by construction |
| [20261007T131202Z-m2-look3-scale.md](20261007T131202Z-m2-look3-scale.md) | `eval/results/20261007T131202Z-m2-look3-scale.json` | The graph signal helps the hybrid more as the corpus grows (-0.022 to +0.039) | Free-form graph; descriptive |
| [20261007T140853Z-m2-look4.md](20261007T140853Z-m2-look4.md) | `eval/results/20261007T140853Z-m2-look4.json`, `20261007T140924Z-m2-audit-sample.*` | The `atomic2` graph and the vault over it (0.2107 to 0.2871; hybrid 0.3496) | 3 papers; still below the no-graph control there |
| [20261014-m2-look5-full-corpus.md](20261014-m2-look5-full-corpus.md) | `eval/results/20261014T151443Z-m2-look5.json` | The `atomic2` graph and the vault over all 16 papers: the vault lifts its own graph signal (+0.034) but `hybrid_vault` is level with its own frozen hybrid and -0.026 below the baseline's; +0.014 over `flat` (descriptive) | 19 questions; one build per graph; two provider routes in two invocations; gate clause 3 fails |
| (D-38, from the row below) candidate depth 30 adopted in the product path only | `eval/results/20261014T135007Z-p3-rerank.json` | `hybrid_n30` against frozen `hybrid`: Recall@10 +0.093 (6 / 12 / 1, p = 0.094), nDCG@10 +0.030 (8 / 4 / 7, p = 0.80) | 19 questions; the depth was chosen post hoc among {10, 30, 50}; exploratory |
| [20261015-ragas-context-metrics.md](20261015-ragas-context-metrics.md) | `eval/results/20261015T054853Z-ragas-original.json`, `20261015T055033Z-ragas-extension.json` | RAGAS 0.4.3 non-LLM context recall and precision are 0.0 for every arm on 38 questions: string similarity cannot see a 200-character passage inside a 1,200-character chunk | secondary only; threshold not tuned; no LLM-judged metric run |
| [20261015-question-set-extension.md](20261015-question-set-extension.md) | `eval/results/20261014T192628Z-extension-pooled.json` (inputs: `...T191800Z-ext-benchmark`, `...T192055Z-ext-rerank`, `...T192526Z-m2-ext`) | 19 declared new questions: depth 30 not confirmed (-0.007 Recall@10, reversed, D-40); hybrid vs flat pooled -0.001 (p = 0.69); vault +0.041 over its own graph (p = 0.34) | 38 questions in two sets; drafter is the system's author; no contradiction questions; no pair significant |
| [20261014-p3-rerank.md](20261014-p3-rerank.md) | `eval/results/20261014T135007Z-p3-rerank.json` | A pretrained cross-encoder re-ranker is not shown to help the hybrid arm (rerank_n50 against hybrid_n50: -0.007 nDCG@10, p = 0.90); candidate depth alone raises Recall@10 0.212 to 0.305 (exploratory) | 19 questions; one generic pretrained model; about 5 s per query on CPU |
| [20261008-p4-v1-formula-probe.md](20261008-p4-v1-formula-probe.md) | `eval/results/20261008-p4-v1-formula-probe.json` | Which formulas the passages state (RRF and BM25: none) | Regex over mangled PDF text: a lower bound |
| [20261008-p4-lab-mutation-suite.md](20261008-p4-lab-mutation-suite.md) | `eval/results/20261007T173611Z-p4-lab-mutations.json` | 120 planted defects, all refused by the stage named; the browser's sandbox and CSP probes | A planted set the project wrote; the independent reviews are the stronger evidence |
| Mutation fact-check suite (P2) | `eval/results/mutation-factcheck.json` | The verbatim-quote check refuses planted defects | Planted set |

## Open limits and assumptions (the ledger the limits chapter is built from; the chapter is [limits.md](limits.md))

| Item | Where | Owner |
|---|---|---|
| The two 100-item link audit samples are unread | `eval/results/20261007T060948Z-m2-audit-sample.md`, `20261007T140924Z-m2-audit-sample.md` | Azim |
| The full-corpus `atomic2` result is within noise and below the free-form baseline's hybrid; **the link audit sample of this build is drawn (2026-10-15, 100 items, seed 20261007) and unread**: `eval/results/20261014T185317Z-m2-audit-sample.md`, key apart in `audit-keys/` | Look 5 | Azim (reading) |
| ~~RAGAS metrics are null~~ **Resolved 2026-10-15**: installed and run; the non-LLM context metrics are 0.0 for every arm (chunk-length mismatch, threshold not tuned); LLM-judged RAGAS not run (needs the seam) | `refdocs/evidence/20261015-ragas-context-metrics.md` | Closed |
| `one_more_word` lint reason is noisy on real data | `refdocs/execution/2026-10-07-m2-lint-screen.md` | Open |
| Quiz wrong answers are chosen without a model: some are too easy | D-35 A8 limits | Open |
| VerifiedLab: a branch off the grid and off the fuzz is not seen (the interface cannot ask for it); the live generator is not built; the lifecycle states beyond `verified` are P4b | D-36 amendment | Open |
| ~~P3: whether a negative result for one trained engine satisfies Objective 03~~ **Resolved 2026-10-15** (supervisor via Azim: a component may be removed or left when tested to no effect, if documented; D-37 Resolved) | `refdocs/evidence/20261014-p3-rerank.md` | Closed |
| ~~A depth-30 hybrid arm as a declared protocol amendment~~ **Resolved 2026-10-15**: not confirmed on the extension questions, reversed (D-40) | `refdocs/evidence/20261015-question-set-extension.md` | Closed |

## Screenshots

`p0-*`, `p1-*`, `p2-*`, `p2b-*`, `p2c-*` (the first phases), `m2-6-*`, `m2-7-*`, `m2-11-*` (the notes view, mastery and review), `q1-*` (the quiz), `p4-v6-lab.png` (a lab).
