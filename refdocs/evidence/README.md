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
| [20261008-p4-v1-formula-probe.md](20261008-p4-v1-formula-probe.md) | `eval/results/20261008-p4-v1-formula-probe.json` | Which formulas the passages state (RRF and BM25: none) | Regex over mangled PDF text: a lower bound |
| [20261008-p4-lab-mutation-suite.md](20261008-p4-lab-mutation-suite.md) | `eval/results/20261007T173611Z-p4-lab-mutations.json` | 120 planted defects, all refused by the stage named; the browser's sandbox and CSP probes | A planted set the project wrote; the independent reviews are the stronger evidence |
| Mutation fact-check suite (P2) | `eval/results/mutation-factcheck.json` | The verbatim-quote check refuses planted defects | Planted set |

## Open limits and assumptions (the ledger the limits chapter is built from)

| Item | Where | Owner |
|---|---|---|
| The two 100-item link audit samples are unread | `eval/results/20261007T060948Z-m2-audit-sample.md`, `20261007T140924Z-m2-audit-sample.md` | Azim |
| The full 16-paper `atomic2` build is not run | P5 F4 | Azim (the cap) |
| RAGAS metrics are null; the library is installed at the end | P5 F5 | Azim's standing instruction |
| `one_more_word` lint reason is noisy on real data | `refdocs/execution/2026-10-07-m2-lint-screen.md` | Open |
| Quiz wrong answers are chosen without a model: some are too easy | D-35 A8 limits | Open |
| VerifiedLab: a branch off the grid and off the fuzz is not seen (the interface cannot ask for it); the live generator is not built; the lifecycle states beyond `verified` are P4b | D-36 amendment | Open |
| P3: whether one trained engine is required (Objective 03) | `refdocs/plans/2026-10-14-p3-trained-tools-deliberation.md` | Azim |

## Screenshots

`p0-*`, `p1-*`, `p2-*`, `p2b-*`, `p2c-*` (the first phases), `m2-6-*`, `m2-7-*`, `m2-11-*` (the notes view, mastery and review), `q1-*` (the quiz), `p4-v6-lab.png` (a lab).
