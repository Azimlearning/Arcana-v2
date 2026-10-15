# P4 V9: a live model writes the lab functions, and the verifier decides (2026-10-15)

Results: `eval/results/20261015T060122Z-lab-live.json` (prompt `live-lab-1`) and `eval/results/20261015T060240Z-lab-live.json` (prompt `live-lab-2`), tool `eval/lab_live.py`, both at a clean commit. Generator: `api/labs/live_generator.py` (one call per attempt through the LLM seam, tier standard, no retry and no feedback from the verifier). Corpus: the 16-paper store; the four contracts' source passages were found in it (`GET /labs`: 4 of 4). Labs were built into a throwaway store. Spend: **$0.0458** for the 15 paid generation calls (including one aborted attempt and one diagnostic), all served by OpenRouter (`anthropic/claude-sonnet-5.5`) because Anthropic's own credit balance is exhausted (every Anthropic attempt is booked as failed at $0).

## Protocol (written before run 1)

Four contracts, two attempts each, one call per attempt, the model given the parameters and the stored passage that states the formula and the language the checker accepts, **not** the reference cases or properties. Measured: the share of first attempts the verifier accepts and the stage of each refusal.

## Results

| Prompt | Accepted | Refusals |
|---|---|---|
| `live-lab-1` | **2 of 8** (cosine distance, both) | RankNet and InfoNCE: `check` (syntax), 4 attempts; F1@k: `reference_cases`, 2 attempts |
| `live-lab-2` | **6 of 8** (RankNet, InfoNCE, cosine distance, both attempts each) | F1@k: `reference_cases`, both attempts |

## What happened, and what it does and does not show

- **The gate is what it was built to be.** The first prompt produced replies that contained a draft, a prose correction and a second function in one answer, and calls written `max(x, 0)` instead of `Math.max`; the AST checker refused every one of them at the `check` stage. A model that wrote a plausible but wrong F1 (no clamp: 1.143 where the formula gives 0.571 for 8 hits, k = 10, 4 relevant) was refused at `reference_cases`, twice. Nothing unverified reached the store as a servable lab.
- **The prompt was changed once, after reading the replies** (one function only, `Math.` prefix), and the second run is reported beside the first, never in place of it. No contract, case or property was changed. Run 2's 6 of 8 is therefore a measurement after one prompt revision, not a clean first trial.
- **F1@k fails both times, for the same reason:** the model implements F1 from the passage without the contract's clamp (hits cannot exceed k or the number of relevant items). That is a contract stricter than the passage's wording, which the verifier correctly enforces. I did not weaken the contract to raise the rate.
- **Not shown:** the rate is over 4 contracts and 8 attempts of one model through one route; it says the gate admits what a real model writes and refuses what it gets wrong, not how good the model is. The lifecycle cache (D-41) means a lab, once verified, is not generated again.
