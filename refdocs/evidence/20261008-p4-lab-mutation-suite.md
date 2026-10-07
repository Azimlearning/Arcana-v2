# P4 VerifiedLab: the mutation suite and the browser checks (2026-10-08)

Commit: see the result file's `commit` field (recorded after the work was committed). Result file: `eval/results/*-p4-lab-mutations.json` (the latest). Run: `uv run python eval/lab_mutations.py --write`. Free: no model call, no embedding.

## What the suite is

`api/labs/mutations.py` runs **120 planted defects through the real stage that must catch each one**. A defect refused by a different stage than the one named counts as a miss, because it would mean the named defence did not hold.

| Family | Planted | Detected | Through |
|---|---|---|---|
| static (network, escape, values, operators, statements, termination, resources, markup, shape) | 84 | 84 | the checker names the rule |
| execution (wrong numbers, non-finite values, a curve of the wrong shape, hidden branches on the grid, too slow) | 14 | 14 | the verifier names the stage |
| tampering (a delivered block changed in one way: source, hash, template version, id, contract, parameters, counts, citation) | 16 | 16 | the delivery gate |
| row tampering (an edited `labs.db` row, with the block edited to match where that matters) | 6 | 6 | the delivery gate |

## What it means, and what it does not

It is **regression coverage of a set this project wrote**, not independent evidence that the gate is sound: a defect nobody planted is not in it. The stronger evidence is the two independent reviews (`DECISIONS.md` D-36 amendment, the execution doc's V8): the adversarial reviewer ran 60,000 mutation-fuzz sources and 400,000 markup-breakout strings against the checker with no bypass of the value or script-breakout rules, and found two blocking problems elsewhere (a float-precision loop bound, and a sampled verifier that missed a hidden branch), both fixed and now in this set. The claim stays "refused every planted defect and survived these reviews", never "proven safe". `node:vm` is not isolation; the process boundary on the server and the sandboxed iframe in the browser are.

**Known unseen:** a branch at a value that is neither a grid point nor in the 200-vector seeded fuzz. The interface cannot ask for such a value (the sliders snap to the grid and the swept axis uses it); a test states this.

## Browser checks (Playwright, 1440 by 900, the 16-paper corpus in fake mode)

The lab made from the passage on page 16 of 2304.09542 renders in an iframe whose `sandbox` is exactly `allow-scripts` and which has no `src`. By keyboard the first slider moves along its 65 grid positions (a position gives `si = 0.75`), and the loss reads 0.8259 where the formula gives `log(1 + exp(0.25)) = 0.8259`. From inside the frame: `fetch` to the API is blocked by the CSP (`default-src 'none'`), `localStorage`, `window.parent.document` and `document.cookie` throw `SecurityError`, changing the top location and opening a popup are blocked (the browser logs each), the origin is `null`. `eval` and `new Function` throw `EvalError` under the CSP (checked from a script inside a sandboxed frame with the same CSP; an earlier probe that said "allowed" ran through the automation's own evaluate call, which is outside the page's CSP, and is not evidence). Screenshot: `p4-v6-lab.png`.

Tests at this point: backend 1310, web 358.
