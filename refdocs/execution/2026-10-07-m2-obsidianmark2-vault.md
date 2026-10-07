# Execution: genui-obsidianmark2, the compiled vault

> Plan: `refdocs/plans/2026-10-07-m2-obsidianmark2-vault.md`. ADR: D-35 (the protocol is fixed there). Tasks run in order. A task is not done until its **Verify** passes, not when the code compiles.
> If reality diverges from this doc, **edit this doc** (CLAUDE.md rule 4) and note it in the changelog's Deviations line.
> Status: **Approved by Azim 2026-10-07 (directions A to G).** M2.1 is next. **M2.5 spends money and needs Azim's confirmation of the amount first.** The monthly cap ($10, $2.4443 left) is Azim's to raise; I cannot edit `.env`.

## Before starting

- Read `CLAUDE.md`, walk `.claude/memory/preflight.md`, `refdocs/STATUS.md`, D-20, D-33, D-34, D-35, `eval/graph_variant.py` (its protocol text), `api/ingestion/atomic.py`, `api/retrieval/{graph,entities,traversal,hybrid}.py`.
- **Frozen, not to be touched:** the pinned stores in `data/eval-live-live`, `eval/questions.yaml`, the manifest, the gold, the frozen graph retriever and resolver constants, `GRAPH_SCORING_VERSION`. `uv run pytest eval/tests/test_frozen_assets.py` runs in every verify.
- Mark 1 data are kept in `data/g1/slice-base` and `data/g1/slice-atomic` (gitignored; graph hashes recorded in the evidence). **Never write to them.** Every new build goes into a new directory.
- Fakes first. Read current library docs (context7 or official) before writing against Next.js, React, Tailwind, Zustand or the Anthropic SDK (CLAUDE.md rule 6).
- A wire change starts in `packages/schema`, then `pnpm codegen`, then `pnpm codegen:check`, then the server validator, then the registry and component with all four states (preflight 5).

---

### Task M2.1: The vault core (direction A, free)

**Files:** `api/vault/__init__.py`, `api/vault/types.py` (`ConceptPage`, `Mention`, `PageLink`, `Claim`, `Vault`), `api/vault/compile.py` (`compile_vault(graph, docs)`), `api/vault/store.py` (`VaultStore` ABC), `api/vault/local.py` (JSON-file implementation), tests.

1. `compile_vault` implements exactly the construction in D-35: pages by union-find over `alias_of` and equal compact ids; mentions found corpus-wide with an inverted token index (so 11k nodes over 1,570 passages is not 17M substring tests); asserted links lifted to pages; co-mention links by sentence with the cap of 6 pages and the person/organisation exclusion; spread weights; a deterministic ordering and a stable hash of the whole vault.
2. `VaultStore` (get page, pages, links for a page, mentions, claims, save), a local JSON implementation, a round trip test. Code calls the interface (constraint 6).
3. A command `uv run python eval/vault_tool.py build --data <dir>` writes `<dir>/vault.json` (never into a frozen directory), prints the structure numbers.

**Verify:** tests on a hand-built graph with known pages, mentions, links and spread (computed by hand in the test); a determinism test (same inputs, same hash; shuffled node order, same hash); hyphen-blind matching; the cap and the exclusion; an empty graph; a `data/eval-live-live`-sized run finishes in seconds and writes nothing to it; the frozen-asset tripwire passes.

**Reality (M2.1 done 2026-10-07):** `api/vault/{text,types,compile,store,local}.py` and `eval/vault_tool.py` (copies a data directory into a new one, never writing to the source, and compiles `vault.json`; checks the copy's graph and vector hashes equal the source's). 21 tests (hand-computed world: aliases to one page, hyphen-blind mentions that do not fire inside "Self-RAG", spread arithmetic, asserted lifting, the co-mention cap at exactly 6 and 7, people excluded, definitions, claims, order-independence of the hash, store round trip, the matcher pinned to the builder's `label_in_text`). **One declared amendment (D-35 A1), made after compiling the vault over the Mark 1 slice and before any retrieval run:** about 16 percent of the first build's 1,633 co-mention links came from reference-list entries, so a sentence with a strong bibliography marker makes no co-mention links ("et al" is deliberately not a marker). Result on the Mark 1 slice (`data/m2/slice-atomic-vault1`, vault sha256 `fa626429...f08bca`): 744 nodes to 725 pages (only 16 pages gained an alias: the text defines few abbreviations), 171 asserted and 1,422 co-mention links, **65.7 percent of pages linked** (73 percent of nodes had no edge in Mark 1), every one of the 285 passages mentioned by at least one page; the most generic pages are "retrieval" (159 of 285 passages), "Retrieval-Augmented Generation" (126), "generation" (118): the spread discount has real work to do. A stale pre-amendment build is in `data/m2/slice-atomic-v1` (gitignored; a deletion was refused by the harness, so it is left and ignored). Verified: `uv run pytest api eval/tests` 910 passed, ruff and pyright clean. **Noted, not changed:** alias grouping by text alone is thin (a rule joining "LLMs" to "large language models" by initials would be a `vault-2` change and a counted look; G1's audit removed such a rule at node level because it lacked textual support).

### Task M2.2: The vault retriever `vault-1` and the compare tool (direction C), then the audit

**Files:** `api/retrieval/vault.py` (`VaultRetriever`, `VAULT_SCORING_VERSION = "vault-1"`, `SemanticResolver`), `eval/vault_compare.py` (new; its module text is the protocol, copied from D-35, and is copied into every result), tests.

1. `VaultRetriever` implements the scoring in D-35 over a `VaultStore` and a `DocStore`, with toggles (co-mentions, spread, claims) for the free ablations. It does not import or edit the frozen graph retriever.
2. The semantic step: page labels embedded once (cached by the existing caching embedder) and stored in the vault directory; rank-based top 2, weight 0.5, only when lexical resolution covered fewer than half of the content words.
3. `eval/vault_compare.py`: runs the frozen `graph`, `hybrid`, `flat` over each directory and the four vault arms over the atomic directories, with the checks of Mark 1's tool (same chunks and vectors, control identical, dirty-tree refusal, protocol stamp, descriptive-only rule) and the Mark 2 gate of D-35, the looks ledger, and the free ablations.
4. **`retrieval-auditor` reviews this task before any run** (fusion untouched, toggles independent, the gate not tautological, the control enforced, the protocol identical to D-35). Its blocking findings are fixed first.

**Verify:** tests for every scoring term by hand (a handmade vault: direct, asserted neighbour, co-mention neighbour, spread, tie-break, rounding), the semantic step on a fake embedder, the toggles, empty-ranking and unresolved queries, the gate arithmetic, a refusal when the protocol text differs from D-35; frozen-asset tripwire; ruff and pyright.

**Reality (M2.2 done 2026-10-07):** `api/retrieval/vault.py` (`VaultRetriever`, `vault-1`, `embed_page_labels`, `labels_sha256`; the frozen retriever and resolver untouched, the resolver reused over the member node ids of every page), `eval/vault_compare.py` (the protocol as its module text, copied into every result; commands `embed-labels`, `compare`, `audit`) and tests (`api/retrieval/test_vault.py` with every score computed by hand, `eval/tests/test_vault_compare.py`). **`retrieval-auditor` reviewed it before any run** and found three blocking defects, all fixed before a run: (B1) failed vault cells were dropped from validity and clause 4, so a broken arm could pass on nothing; a failed cell now invalidates the arm, a missing measure never passes, zero answerable questions is refused; (B2) label vectors had no provenance, so fake vectors could be compared with live question embeddings; they now carry mode, model, dimension and a label hash and are refused on any mismatch; (B3) the gate's outcome was largely known before the run and D-35 did not say so: clause 3 cannot move at Look 2 and is expected to fail by construction (disclosed in D-35 A3). Non-blocking items fixed: the vault must belong to its directory; the 6-page cap counts every page named (A3; vault rebuilt: 1,406 co-mention links, 65.5 percent of pages linked); a label with no ASCII alphanumeric token is scanned; claims are sorted; the audit hides the kind and keeps its key apart; a live run checks the frozen assets and approved gold; the semantic arms are required unless `--without-semantic` is given, and then the result says the protocol is incomplete; headline pairs named; two numbers in A1 and A2 corrected. **A slip of mine, caught at once:** a `ruff format` over the whole `api` directory reformatted 66 unrelated files (the repository is not ruff-formatted); they were restored with `git checkout` before anything was committed, and only named files are formatted now. Verified: `uv run pytest api eval/tests` (see the commit), ruff and pyright clean.

### Task M2.3: Look 2, the vault over the Mark 1 graph (free)

**Files:** `eval/results/<stamp>-m2-look2.json`, `refdocs/evidence/<stamp>-m2-look2.md`, the audit sample.

Build the vault over `data/g1/slice-atomic` and `data/g1/slice-base`, run the compare, write the evidence record with the commit, hashes, gate, per-arm paired differences and the ablations. The only paid element is the question embeddings (cached from Mark 1 where the text matches; the amount is read from the ledger and reported). Page-label embeddings are under $0.001. **Azim is told the amount before the run if it is not zero.**

**Verify:** the results reproduce on a second run; the flat control identical; the pinned and Mark 1 hashes unchanged before and after.

**Reality (M2.3 done 2026-10-07):** the page labels were embedded ($0.000381) and the compare run on commit `92624f7` ($0.000064 for 19 question embeddings; $0.000445 in all; month total $7.556145). Result and reading in `refdocs/evidence/20261007T060911Z-m2-look2.md`. **Headline:** the vault is a clearly stronger graph signal (`vault` against the frozen `graph` over the same nodes: nDCG@10 0.1408 to 0.2268, 8 better, 10 tied, 1 worse) and does not improve the hybrid (0.3706 to 0.3454, 5 better, 7 worse); the `flat` control (0.3826) is still best; the spread discount carries the gain; the semantic step hurt; clause 3 of the gate failed by construction as D-35 A3 had said. The 100-item link audit sample (kind hidden, key in `eval/results/audit-keys/`) is for Azim; my read of 24 items found the asserted links good and the co-mention links noisy (reference titles without a marker). `vault-2` candidates are recorded, not applied.

### Task M2.4: The builder `atomic2` on fakes (directions B and D)

**Files:** `api/ingestion/atomic2.py`, an `ExtractionResult.claims` field (optional, default empty), `IngestDeps.builder` value `atomic2`, a fake extractor, tests, `api/core/settings.py` (the builder setting accepts the new value).

1. Server-side segmentation of each passage into numbered sentences (verbatim spans of the whitespace-normalised chunk; sentences shorter than the minimum quote length are not numbered).
2. The prompt `g2-1` (written before any live run and frozen with the protocol): the model returns concept labels with kinds, typed relations with an optional sentence number, and claim sentence numbers. The server finds the sentence, checks the labels, applies the two-sentence window, builds notes and evidence from the passage's own words, and counts every drop and every correction under a reason.
3. Claims: a sentence the model named that holds the label of at least one kept concept; at most 6 per passage; stored in the vault, never in the graph.
4. Aliases from defining sentences (`with_aliases`) apply as in g1-3.

**Verify:** tests for each drop reason and correction, the window, the claim rules, a hand-built passage with known output, the fake LLM path through `build_graph`, the cost estimate (worst case reserved per call) consistent with the ledger, old stores and `atomic` unchanged; ruff and pyright.

**Reality (M2.4 done 2026-10-07):** `api/ingestion/atomic2.py` (builder `atomic2`, prompt `g2-1`, its SHA-256 pinned in a test), `ExtractionResult.claims`, `IngestDeps.builder = "atomic2"` and `IngestDeps.claim_sink`, the fake LLM's `fake_atomic2_responder` (dispatched on its own marker), `graph_variant.py rebuild --builder atomic2` (writes `claims.json` beside the graph) and `vault_tool.py build` (reads it). 17 builder tests and one rebuild-to-vault test, every expected value worked out by hand from one handmade passage: the server chooses a concept's note (first sentence holding the label, a definitional cue preferred, clipped on a word boundary to 240 characters and the label must survive the cut), a relation's evidence (the model's number is tried first, then any sentence, then any adjacent pair, pairs over 240 characters are not used) and a claim (a sentence naming at least one kept concept, at most 6); every stored sentence is a verbatim span of the normalised passage; each drop and each correction has a counted reason. The model's numbers are hints and are never trusted. **Two hand-calculation slips fixed in the tests, not the code:** a hint that names either sentence of an adjacent pair counts as the model's own window (no correction), and an out-of-range or boolean number is "no usable number". Verified: `uv run pytest api eval/tests` 965 passed, ruff and pyright clean. The ingestion hook that stores claims in a real ingestion (not a variant rebuild) is part of M2.8.

### Task M2.5: The paid rebuild with `atomic2` and Look 3 (PAID)

**Needs Azim's confirmation of the amount and the ceiling first.** Expected $0.7 to $1.1 for the 285 passages (assumed; the Mark 1 builder measured $1.0879); the tool takes `--max-usd` and enforces it per call; the ledger refuses past the cap ($2.4443 left). A one-paper pilot is **not** repeated: the prompt differs, but the Ragas paper was already the pilot for the pipeline; the first document built is examined for defects only, as in Mark 1, and any change is a declared amendment with a new prompt version before the other papers are built.

**Verify:** the build record complete; spend equals the ledger; then the compare as in M2.3 with the third directory; the evidence record states the looks count.

### Task M2.6: The notes view (direction E)

**Files:** `packages/schema` (new block variants, designed at the start of this task after reading `web/`, the Composer and the TraversalView pattern), generated Pydantic, `api/genui/{catalog,templates,validate}.py` (catalog entry with a written structural precondition, fences, registration defects), `api/agents/compose.py`, a vault route, `web/components/genui/` (page, local graph, backlinks, unlinked mentions), the registry, the Studio hook, tests, a real-browser run.

Design intent (refined at the start of the task): a **ConceptPage** block (aliases, defining sentences with citations, backlinks, typed links, claims, unlinked mentions) and a **NotesGraph** block (pages as nodes, a local graph one or two hops out, sized by passage count), both validated server-side by **re-deriving them from the vault** (as TraversalView is), fail-closed, rendered only through the registry with the four states. TraversalView paths link to pages.

**Verify:** `pnpm codegen:check`; server tests (validator rejects planted defects; the registration suite plants one defect per fence); `pnpm -r test`, lint, typecheck; a real-browser screenshot in the evidence folder; `schema-guardian` review.

### Task M2.7: The learner layer (direction F)

**Files:** a `LearnerStore` abstraction and local SQLite implementation, an events route (self-rating; later quiz results), mastery on `ConceptPage` and in `NotesGraph` colouring, schema and validators, tests.

Mastery per concept page from events (a documented, deterministic update, e.g. a Beta-style count with decay), with the update rule written in the ADR addendum before it is built. Stored locally; events only; deletable.

**Verify:** update-rule tests by hand; the route validates and fails closed; colouring appears in a real-browser run; no secret or personal data is logged.

### Task M2.8: Lint and compounding (direction G)

**Files:** `api/vault/lint.py`, the ingestion hook that recompiles the vault, tests.

Lint reports: orphan pages, near-duplicate pages awaiting review (deterministic similarity, never merged), pages defined differently in different papers (reported as a tension candidate, not judged), hub pages. A new document recompiles the vault (`delete_document` plus compile). Contradiction judging by a model is **not built** and is listed as a known gap.

**Verify:** tests on hand-built vaults; recompiling after adding and deleting a document gives the same vault as compiling from scratch.

### Task M2.9: Reviews

`retrieval-auditor` (before M2.3 runs, repeated for `atomic2`), `cost-auditor` (before M2.5), `schema-guardian` (M2.6, M2.7), `test-runner` (full suite, codegen drift, build). Fix blocking findings; record the rest.

### Task M2.10: Docs and close

Changelog entry, STATUS, ADR addenda (the learner update rule; anything that moved), execution doc Reality notes, the plans and execution READMEs, `catalog.md`, `file_structure.md`, the memory note. Commit locally; **do not push** until Azim says.
