# Execution: P4 VerifiedLab, the first slice

> Plan: `refdocs/plans/2026-10-08-p4-verifiedlab.md`. ADR: D-36. Tasks run in order. A task is not done until its **Verify** passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **V1 to V8 built, reviewed and checked (2026-10-08); V9 (the live generator) not started.** Free through V8. V9 is paid: cost audit and Azim's confirmation first.

## Before starting

- Read `CLAUDE.md`, `.claude/memory/preflight.md`, D-10, D-31 and D-36, the catalog guide's "UI generation pipeline" and "Where P4 plugs in", `api/genui/{catalog,templates,validate}.py`, `web/components/genui/registry.tsx`.
- **Read the current docs before using a library** (CLAUDE.md rule 6): Node's `vm` module and `child_process` (the page says `vm` is not a security mechanism), `acorn`'s API and node types, and MDN for `iframe sandbox`, `srcdoc` and `Content-Security-Policy` in a `<meta>`. Do not write against these from memory.
- Order for every wire change: `packages/schema`, `pnpm codegen`, `pnpm codegen:check`, the validator, then the registry entry and component with all five states.
- Only files I create are formatted with `ruff format`.

### Task V1: probe, contract and schema

**Files:** `eval/lab_probe.py` (a free, read-only probe), `api/labs/contract.py`, `packages/schema/src/{payloads,blocks}.ts`, generated Python, the catalog guide.
1. Probe (no model): find which candidate formulas appear with their symbolic form in the stored passages of the 16-paper corpus; record the passage ids and the sentences. **Done 2026-10-08** (`refdocs/evidence/20261008-p4-v1-formula-probe.md`): RRF and BM25 are absent, the RankNet pairwise loss, pointwise BCE, InfoNCE and the answer-relevance average are present; the first contract is the RankNet loss.
2. `LabContract` (Pydantic, server-side): `id`, `title`, `parameters` (name, min, max, default, unit; at most 4), `outputs` (names of the arrays returned), `domain_points` (how many sample points), `source` (a passage citation holding the formula), `reference_cases` (params and expected arrays with a tolerance), `properties` (named checks: `finite`, `bounded(a, b)`, `monotone(param, direction)`, `matches_reference(python_fn)`).
3. Wire: block `VerifiedLab` with `VerifiedLabData { labId, title, parameters[], outputs[], source, sourceSha256, templateVersion, citations[], checked: {referenceCases, properties, fuzzCases} }`. The `source` field is the verified function text: inert data until the host puts it in the sandbox.

**Verify:** the probe's result is in an evidence file; the contract rejects a malformed declaration (missing range, `min >= max`, more than 4 parameters); `pnpm codegen:check` is clean.

### Task V2: the checker (static analysis)

**Files:** `packages/labs-check/` (a pnpm workspace package: `acorn` and `check.mjs`), `api/labs/checker.py` (calls it), tests.
1. `check.mjs` parses the source with `acorn` (ecmaVersion fixed, no modules) and accepts only the allowlisted node types and identifiers; every rejection names the node and the rule.
2. The allowlist is a data file (`allowlist.json`) so it is one reviewable list: arithmetic and comparison operators, `Math.<abs|min|max|pow|sqrt|exp|log|sin|cos|tan|floor|ceil|round|PI|E>`, `const`/`let`, `for` with a literal upper bound at most 10,000, `if`, array literals and numeric indexing, `.length` on arrays the function made, one `function lab(params)` and `return`.
3. Everything else is rejected, in particular: any other identifier (`window`, `globalThis`, `self`, `process`, `require`, `fetch`, `eval`, `Function`, `constructor`, `__proto__`, `prototype`), computed property access with a non-numeric key, `new`, `import`, `class`, `async`, `await`, `yield`, generators, template literals with expressions, `with`, `debugger`, labels, regular expressions, `try` (no catching what the verifier must see), `while` and `do` (no unbounded loops), recursion.

**Verify:** by-hand tests for each allowed construct and each rejected one; the allowlist file is checked against the guide by a parse (as the catalog fences are).

### Task V3: the verifier and the mint

**Files:** `packages/labs-check/run.mjs`, `api/labs/verifier.py`, `api/labs/artifact.py`, `api/labs/store.py` (the `labs` table: id, source, hashes, report, state), tests.
1. `run.mjs` runs the function in `node:vm` in a child process: a null-prototype context with only `Math`, no `require`, frozen intrinsics, a wall-clock limit (1 s), an output size cap, a memory limit (`--max-old-space-size`), no network (the process has no module to open one). It returns numbers or a named failure (`timeout`, `non_finite`, `too_large`, `threw`).
2. `verifier.py` runs the checker, then the child on the reference cases, the properties and a fuzz of parameter vectors (edges of each range, midpoints, seeded random), compares with the Python reference, and **only if everything passes** constructs `VerifiedArtifact` using a module-private token. The class cannot be built elsewhere (constructor refuses without the token; a test tries every way).
3. The store records `generated` and `verified` (D-31's later states are P4b) with the report.

**Verify:** a correct function passes; each failure class gives its named failure; `VerifiedArtifact(...)` outside the verifier raises; two runs of the same source give the same report.

### Task V4: the delivery gate

**Files:** `api/genui/{builders,validate,notes_catalog or a labs registry}.py`, `api/agents/compose.py` (`compose_lab`), `api/routes/labs.py` (`POST /labs`, `GET /labs/{id}`), `api/main.py`.
1. The builder for `VerifiedLab` accepts only a `VerifiedArtifact`. The validator re-derives the block from the stored verified record by `labId` and requires equality (source, hash, template version, parameters, checked counts, citations); a missing record, a changed byte, a stale template version or a status other than `verified` is refused. It fails closed on any store error.
2. A test enumerates every emitter of blocks (routes and the stream) and asserts a `VerifiedLab` can only leave through `validate_block`; a second test tries to forge one (a hand-built dict, a changed hash, an unverified record).

**Verify:** the planted tamper cases are rejected; the enumeration test fails if a new route emits blocks without the validator.

### Task V5: the fake generator and `compose_lab`

**Files:** `api/labs/generator.py`, `api/fakes.py`, tests.
1. A `LabGenerator` interface (constraint 6): the fake returns a deterministic function for each known contract (and a configurable defective one for tests); the live one calls the LLM seam and is built in V9, not here.
2. `compose_lab(contract_id)` generates, verifies, stores and returns the block through the gate; a failure at any stage is an `error` block with the stage's reason, never a half-built lab.

**Verify:** the happy path returns a `ready` block; each stage's failure returns an error block naming the stage; nothing reaches the client unverified.

### Task V6: the web host

**Files:** `web/components/genui/VerifiedLab.tsx`, `web/lib/labFrame.ts` (the pinned template and its hash), `registry.tsx`, `lib/store.ts`, tests.
1. The component builds `srcdoc` from the pinned template plus `block.data.source`, after checking `sha256(source) === sourceSha256` and `templateVersion` equals the client's; it renders `<iframe sandbox="allow-scripts" ...>` with no other token and a `<meta>` CSP `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'`.
2. The template draws sliders for the declared parameters, calls `lab(params)` and plots the arrays on a canvas; it shows the contract's title, the source citation text outside the iframe (document text as text), and what was checked ("verified on N reference cases, M properties and K fuzzed inputs; not a proof for every input").
3. Five states; keyboard-operable sliders with labels; the plot has a text equivalent (a table of values).

**Verify:** the iframe's `sandbox` attribute is exactly `allow-scripts` (test); a mismatched hash renders an error state and no iframe; component tests for every state.

### Task V7: the mutation suite and the real-browser run

**Files:** `api/labs/mutations.py` (the planted set), `eval/lab_mutations.py`, tests, `refdocs/evidence/<date>-p4-mutation-suite.md`.
1. At least 25 planted defects, each tagged with the stage that must reject it: network (`fetch`, `XMLHttpRequest`, `WebSocket`, `import()`), escape (`constructor.constructor`, `this`, `globalThis`, `__proto__`, `Function`), storage and DOM names, non-termination (a huge loop, recursion, `while`), resources (a giant array, a long string), numeric (returns `NaN`, `Infinity`, a wrong formula, a wrong range, violates monotonicity), tampering (a changed hash, a changed template version, a swapped source).
2. `eval/lab_mutations.py` runs the set and writes the detection rate per class and overall; **the set's limits are stated in the evidence** (it is the planted set, not all possible attacks).
3. Real browser: a verified lab renders and works; planted artifacts that the server would refuse are loaded directly into the host to show the sandbox and CSP also hold (a `fetch` fails, `parent` access fails, `localStorage` throws).

**Verify:** every planted defect is rejected by its named stage (a test); the evidence file records the rate and the limits; screenshots in `refdocs/evidence/`.

### Task V8: review and close

`schema-guardian` (wire change; the gate; registry completeness) and a second, security-minded review of the checker, the verifier and the sandbox host; the catalog guide section for `VerifiedLab`; full suites; changelog, STATUS, indexes; commit locally. Anything blocking is fixed before V9.

### Task V9 (paid, later): the live generator

Not started until V1 to V8 are green and Azim has confirmed an amount. `cost-auditor` first; the generator goes through the LLM seam and the ledger, the same gate, a hard ceiling, and a recorded success rate (how often a generated function passes the gate) and cost per lab.

## Reality

Status: **V1 to V8 built and checked (2026-10-08).** Free throughout (fakes only).

- **V1 (probe and contract).** The probe (`eval/lab_probe.py`) found that **reciprocal rank fusion and BM25 are in no stored passage**; the corpus holds the RankNet pairwise loss, pointwise BCE, InfoNCE and the answer-relevance average (`refdocs/evidence/20261008-p4-v1-formula-probe.md`). The first contract is the RankNet loss. `api/labs/contract.py`: `LabContract` and its parts, validated when made (finite ranges, at most 4 parameters, a cited source phrase of at least 20 characters, a known reference function, reference cases inside the ranges); the **function is scalar**, `lab(p) -> number`, and the plot is a sweep of one declared parameter made by the host, which makes the generated surface smaller than the plan said (no arrays). The contract names a **source phrase** instead of a passage id: the phrase is found in the stored passages at generation time, so the code holds no corpus ids. 30 tests, with the four reference values worked out by hand.
- **Deviation 1: the wire type moved from V1 to V4.** Adding `VerifiedLab` to the `UIBlock` union before its validator and component would break the build between tasks; it is added in V4 together with the validator and a web stub, in the order the project requires (schema, codegen, validator, registry and component).
- **Deviation 2: no arrays in the subset.** The plan allowed array literals and numeric indexing. While writing the allowlist, computed indexing turned out to be a way to rebuild property names from coerced values (a known JavaScript trick), so the subset has **no arrays, objects, strings or computed access at all**: the only values are numbers and booleans, the only member accesses are `p.<declared parameter>` and `Math.<listed>`, so nothing but numbers can exist to reach a prototype from. The plan's loop-over-an-array use case is covered by bounded numeric `for` loops.
- **V2 (checker).** `packages/labs-check/` (a pnpm workspace package; `acorn` 8.19.0, exact, MIT; its README read first), `check.mjs` and `allowlist.json` (one reviewable list), `api/labs/checker.py` (calls it as a subprocess, a missing or confused tool is a refusal, never a pass). `api/labs/planted.py` holds **73 planted static defects** in eight classes (network, escape, values, operators, statements, termination, resources, shape), each with the rule that must reject it; all are rejected (113 tests with the accepted constructs). Five defects are rejected by a different rule than I first named (for example `globalThis.x` is stopped by the member rule before the identifier rule); the set names the rule that actually fires.
- **V3 (verifier, runner, mint, store).** `run.mjs` runs the function in `node:vm` in a child process under a memory limit and time limits; the Node documentation (read first: "The node:vm module is not a security mechanism. Do not use it to run untrusted code") is why it is a correctness and resource harness and not the isolation claim, and the file says so. `api/labs/verifier.py` runs the checker, then a battery (the reference cases, a sweep of every parameter with the others at default, minimum and maximum, the 3 x 3 corners and 200 seeded fuzz vectors, all in one runner call), then the properties and the Python reference, and only then mints `VerifiedArtifact`. The mint is a module-private token; the class cannot be changed, copied or deep-copied (both refuse), and a test scans `api/` and `eval/` for any other construction or use of the token. **Stated limit:** that is a checkable convention, not a language guarantee; Python cannot stop code in the same process from forging an object, and this process never runs generated code; the downstream line is the store (it refuses a hash that does not match) and, in V4, the block validator. `api/labs/store.py`: `LabStore` and a SQLite `labs.db` that accepts only a minted artifact, keeps rejected sources as an audit trail and never serves them. 14 tests; the labs suite is 127 tests.
- **Dependency added:** `acorn` 8.19.0 in `packages/labs-check` (D-36 `ASSUMED:` row), `pnpm-lock.yaml` updated.

- **V4 (delivery gate).** Wire: `VerifiedLabData`, `LabParameter`, `LabChecked`, the `VerifiedLab` block and `LabRequest` (schema first, codegen fresh). `api/genui/lab_catalog.py` (its own registry, like the notes components), `verified_lab` (the builder accepts only a `VerifiedArtifact`), `_verified_lab_issues` in `validate.py` (re-derive from the stored verified record and require equality; fail closed), `compose_lab` (evidence, generator, checker, verifier, mint, store, validator; a failure is an `empty` or `error` block naming the stage, never a half-built lab), `POST /labs` (4 KB limit), the container (a fake generator in fake mode, **none in a live mode**: a lab is then refused, never faked). `api/labs/generator.py` (the interface and a deterministic fake), `api/labs/evidence.py` (the evidence precondition and the block data). Tests: 16 forgeries, tamper and no-store cases, a repository scan that only gate modules name the block, and the route and chat-stream checks.
- **V5 (fake generator, `compose_lab`).** Folded into V4 (the gate cannot be tested without it).
- **V6 (web host).** `web/lib/labFrame.ts` (the fixed template; `LAB_SANDBOX = "allow-scripts"`; a CSP of `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'`; the hash, version and markup checks before a `srcdoc` is built), `VerifiedLab.tsx` (five states; the code only in the iframe; document text as text), `web/app/labs/` (a screen to ask for a lab), the registry, the store, fixtures and tests. A fingerprint test pins the template's text to its version.
- **V7 (mutation suite and real browser).** `api/labs/mutations.py` runs **120 planted defects in four families through the real stage that must catch each** (84 static, 14 execution, 16 forgeries of a block, 6 edits of a `labs.db` row): all refused by the named stage; recorded in `eval/results/` and `refdocs/evidence/20261008-p4-lab-mutation-suite.md`. Real browser (Playwright, 1440 by 900, the 16-paper corpus in fake mode): the lab made from the passage on page 16 renders, the sliders (grid indexes) move by keyboard and the loss matches the formula (`log(1 + exp(0.25)) = 0.8259` at `si = 0.75, sj = 1`); inside the frame a network fetch (blocked by the CSP), `localStorage`, `parent.document`, `document.cookie`, top navigation and a popup are all blocked (the browser logs each), the origin is `null`, and `eval` and `new Function` are blocked by the CSP (a first probe reported `eval` allowed only because the Playwright call runs outside the page's CSP; the check was redone from a script inside a sandboxed frame with the same CSP). `refdocs/evidence/p4-v6-lab.png`.
- **V8 (reviews) and what they changed (deviation 3).** Two independent reviews of the built slice: `schema-guardian` (no blocking finding; five should-fix items) and an adversarial reviewer told to break the checker and the verifier (60,000 mutation-fuzz sources, 400,000 markup-breakout strings, no checker bypass of the value or script-breakout rules, but **two blocking findings and five should-fix**). All were fixed: (a) **a loop the checker counted as 10 iterations never ended** (float precision at 1e16): loop literals are now integers of bounded size, so the count is exact; plus a total cap of 20,000 iterations over all loops and a 50 ms limit on one call; (b) **a source that matched the reference on the sampled battery but hung or returned a wrong number at one slider position was VERIFIED**: the verifier now runs every grid combination (a contract has a `grid`, the sliders are grid indexes), so every input the interface can ask for is verified (`checked.gridPoints`, 4,225 for the RankNet lab); (c) loop counters could shadow `Math` or `p`: they now obey the name rules; (d) the mint could be forged three ways: the token lives in a closure, the class cannot be subclassed; (e) the store did not tie the id to the hash and replaced labs: it does and it does not; (f) the gate trusted the stored row: it re-hashes and re-checks the source and compares a contract fingerprint; (g) a lone surrogate raised an uncaught error: it is a named refusal; (h) the on-screen text said "a model wrote" a fixture: reworded; (i) docs said "hash-pinned template": now "fixed and versioned" with a fingerprint test; the schema header now states the one declared exception to "data only"; the CSP gained `base-uri` and `form-action`; the template version is 2. **Honest limit kept:** a branch at a value off the grid and off the fuzz is not seen, and the interface cannot ask for it (a test states this). I also ran `ruff format` over two existing files by mistake (the repository is not ruff-formatted) and reverted them to their committed text before re-applying my edits.
- **Not built:** the live generator (V9, **built and measured 2026-10-15**, `refdocs/evidence/20261015-lab-live-generator.md`), the lifecycle states beyond `verified` (P4b, **built 2026-10-15**, D-41), a lab in a chat turn (the Composer never offers it; the Lab Builder as an agent), more contracts (pointwise BCE, InfoNCE, the answer-relevance average are next), a rate limit or cache on `POST /labs` (relevant once it spends money), Node's permission flag for the runner (a possible extra hardening).
