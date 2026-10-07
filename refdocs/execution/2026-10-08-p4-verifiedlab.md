# Execution: P4 VerifiedLab, the first slice

> Plan: `refdocs/plans/2026-10-08-p4-verifiedlab.md`. ADR: D-36. Tasks run in order. A task is not done until its **Verify** passes.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **Draft (2026-10-08); V1 next.** Free through V8. A live generation run (V9) is paid: cost audit and Azim's confirmation first.

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
1. The component builds `srcdoc` from the pinned template plus `block.data.source`, after checking `sha256(source) === sourceSha256` and `templateVersion` equals the client's; it renders `<iframe sandbox="allow-scripts" ...>` with no other token and a `<meta>` CSP `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'`.
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
