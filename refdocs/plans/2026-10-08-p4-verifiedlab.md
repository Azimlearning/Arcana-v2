# Plan: P4 VerifiedLab, the first slice (a generated function that only a verifier can let through)

> Execution doc: `refdocs/execution/2026-10-08-p4-verifiedlab.md`. ADR: D-36 (with `ASSUMED:` rows for Azim to confirm). Scope source: PRD §6 P4 and D-10, D-31, D-30, hard constraint 3.
> Status: **Draft (2026-10-08).** Approved to start by Azim ("Okay sure proceed", 2026-10-08) on the recommendation to plan P4 first. **Planning is free; building is free on fakes; a live generation run is paid and needs Azim's confirmation of the amount.**

## Why this exists

Generative UI has three levels. Levels 1 and 2 (typed blocks, a typed layout) are built. Level 3 is the one that makes the project's safety argument non-trivial: an interactive artifact that is *generated*, so no one wrote it, yet is shown to the user. The rule (hard constraint 3, D-10) is that generated code reaches the client **only as a type that the verifier alone can mint**, rendered in an iframe with `sandbox="allow-scripts"` and nothing else, with libraries from a local directory and never a CDN. Until this exists, the paper's central claim (retrieval structure bounds what the interface can honestly show, including generated parts) rests on levels 1 and 2 only.

The risk is scale: a general "generate any interactive app" tier cannot be verified. So the first slice makes the generated part **as small as it can be and still be generated code**, and spends the effort on the gate, which is what the project is about.

## What's already covered (no work needed)

The typed block pipeline (schema, codegen, `validate_block`, the registry, placement hints, five render states); the pattern pipeline stages `template, fences, checking, save, reuse` (D-31) that P4 extends; the notes registry pattern (a block re-derived from a record and required equal); spend through the LLM seam and the ledger; fakes by default (`ARCANA_LLM_MODE=fake`); the real-browser run routine. P4 adds `api/labs/` (PRD §3) and one web component.

## Scope

**In (this slice):**
1. A **contract**: what a lab promises, as data (parameters with ranges, the output, a cited source passage, reference cases, properties).
2. A **generated part that is one pure function** in a restricted JavaScript subset. The interactive chrome (sliders, plot, readout) is a **fixed, hash-pinned template we wrote**, never generated.
3. A **checker** (static analysis by an AST allowlist) and a **verifier** (runs the function in a locked-down `node:vm` child on the contract's reference cases, properties and a fuzz of parameters, with time and memory limits) that is the **only code able to create** the `VerifiedArtifact` type.
4. A **delivery gate**: a `VerifiedLab` block carries the verified source, its hash and the contract summary; the validator re-derives it from the verified record and refuses anything else; a test proves no path to the client bypasses the verifier.
5. A **web host**: the `VerifiedLab` component builds its iframe from its own pinned template plus the verified function, `sandbox="allow-scripts"` only, a CSP that forbids network, a hash check before it renders.
6. A **mutation suite**: planted defective artifacts (network, escape, non-termination, wrong numbers, ...), each of which must be rejected by a named stage; the detection rate is recorded.
7. A **fake generator** (deterministic) so everything runs and is tested at no cost; the live generator goes through the LLM seam behind the same gate.

**Out, with reasons:**
- Arbitrary generated UI (React, DOM, canvas code): cannot be verified with a bounded effort; the template is fixed so the generated part has no DOM access at all.
- The governed lifecycle's later states (`cached`, `audited`, `promoted`), eviction, staleness on a model change, and crystallisation into a level 1 component: a second slice (P4b), after the gate is proven. This slice has `generated` and `verified` only.
- Libraries: none are needed for one function and a template-drawn plot; the local vendor directory and its allowlist are created empty and tested (a reference to a URL or an unlisted library is rejected), so the rule exists before anything uses it.
- A live paid generation run and its evaluation (generation success rate, cost per lab): after the gate is green on fakes, with a cost audit and Azim's confirmation first.
- The Lab Builder as an agent: D-30 says growth is by tools; this slice is a tool (`compose_lab`) behind a route, and routing to it from the Orchestrator is a later step.

## Approach

- **Small generated surface.** The artifact is `lab(params)`: a pure numeric function over the contract's declared parameters returning arrays of numbers. It cannot touch the DOM, the network, storage, time or randomness, because the subset has no names for them.
- **Allowlist, not blocklist.** The checker parses with an AST and accepts only listed node types and identifiers (arithmetic, comparisons, `Math.<listed>`, local `const`/`let`, bounded `for` loops, array literals and indexing, one function declaration). Anything else, including every property access outside the list, is rejected. A subset that is wrong in the checker's favour fails closed.
- **Execution is a second, independent line.** Even a function that passes the checker is run only in a child process under `node:vm` with a null-prototype context, no `require`, frozen globals, a wall-clock limit and a memory limit; the verifier compares its numbers with the contract's references and properties and with a Python reference implementation of the same formula.
- **The mint is the gate.** `VerifiedArtifact` can only be constructed inside the verifier module (a private token); the block builder accepts only that type; the validator re-derives the block from the stored record by `labId` and requires equality (the pattern used by `ConceptPage`), so a forged block, a modified source or a changed template version is refused.
- **Honest limits stay on the screen.** The lab says it is generated and verified against stated reference cases and properties, which is not a proof of correctness for every input.
- **Domain (assumed, to confirm; narrowed by the V1 probe).** The corpus is retrieval papers, so the first contracts are **scoring and loss formulas that appear, with their symbolic form, in the stored passages**: they have a cited source, closed-form reference values and checkable properties (non-negativity, monotonicity). This replaces the PRD's "physics contract" example (Q-06), which the corpus cannot satisfy. The V1 probe (`refdocs/evidence/20261008-p4-v1-formula-probe.md`) found that the formulas the plan first named (reciprocal rank fusion, BM25) are **not** in any stored passage; what is there is the RankNet pairwise loss, pointwise BCE, InfoNCE and the answer-relevance average. The first contract is the RankNet pairwise loss.

## Cost estimate

Fakes: nothing. Live generation: one model call per lab (a short function plus its explanation); to be projected per call by `cost-auditor` and bounded by `LLM_MONTHLY_CAP_USD` before any live run, and Azim confirms the amount first. The October cap has about $1.54 left, so a live run waits for the cap to be raised or the 2026-11-01 reset unless the run is tiny.

## Risks & unknowns

| Risk | Impact | Confidence / mitigation |
|---|---|---|
| The AST allowlist has a hole (a way to reach `constructor`, a prototype, or a global) | High: the safety claim | Medium. Two independent lines (allowlist, then a locked `vm` child), plus the iframe sandbox and CSP as a third; the mutation suite is built from known escape routes and grows when one is found; the claim is stated as "tested against this set", never "proven" |
| `node:vm` is not a security boundary on its own | High | Known (the Node docs say so). It is used as a *correctness and resource* harness inside a child process with limits, not as the isolation claim; isolation rests on the sandboxed iframe in the browser and the child process on the server |
| A function passes the contract's reference cases but is wrong elsewhere | Medium | Properties and a fuzz catch classes of error; the screen says what was checked; reference cases come from the cited passage where it gives numbers |
| A parser dependency (`acorn`) enters the repository | Low | MIT, no dependencies; current docs are read before use (CLAUDE.md rule 6); pinned in `pnpm-lock`; recorded in D-36 as an `ASSUMED:` row |
| The first slice is too narrow to be called level 3 | Medium | It is a real generated function behind the full gate with a recorded detection rate; breadth comes by adding contracts and subset members, each with planted defects, not by loosening the gate |
| `sandbox="allow-scripts"` plus `srcdoc` behaves differently across browsers | Low | Seen in a real browser with planted escape attempts; the check is recorded as evidence |

## Definition of done

- No path to the client bypasses the verifier: a test enumerates the routes and the stream and shows a `VerifiedLab` block cannot be built or accepted except from a `VerifiedArtifact` minted by the verifier.
- The mutation suite (at least 25 planted defects across the network, escape, termination, resource, numeric and tampering classes) is run and **every defect is rejected by the stage named for it; the detection rate and the set's limits are recorded** in an evidence file.
- The lab renders in a real browser inside an iframe whose `sandbox` is exactly `allow-scripts`, with a CSP forbidding network; planted escape attempts (network call, parent access, storage) are seen to fail.
- A tampered block (changed source, changed hash, stale template version) is refused by the validator and by the web host.
- Fakes only so far: spend is zero; any live run has a cost audit and Azim's confirmation first.
- Docs current: this plan and the execution doc, D-36 and its `ASSUMED:` rows, the catalog guide section for `VerifiedLab`, changelog, STATUS.
