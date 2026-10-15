# Plan: P4b-lite, the governed lifecycle for verified labs (D-41)

> Execution doc: `refdocs/execution/2026-10-15-p4b-lab-lifecycle.md`. ADR: D-41. Scope source: PRD §3 "Governed lifecycle" and §6 P4; D-11, D-36. Extends the P4 first slice (D-36), where a lab is only `verified` or `rejected`.
> Status: **Built (2026-10-15).** Started on Azim's "lets proceed with the dev, complete it today". No model call and no spend: everything here is local state and the existing local verifier.

## Why this exists

The PRD promises that every generated artifact moves generated, verified, cached, audited, promoted, with flags that evict and version changes that mark artifacts stale (constraint 7: patterns enter the vocabulary only through the governed lifecycle). The P4 slice stores a verified lab and regenerates on every request: it neither reuses a lab (so a live generator would be paid again for the same contract) nor ever retires one. P4b-lite gives the stored labs a small, tested state machine and a cache path, so the lifecycle is real behaviour, not a sentence in the PRD.

## Scope

**In:**

- **States** (stored; `generated` is the transient state before the verifier): `verified`, `cached`, `audited`, `promoted`, `evicted`, `stale`, plus the existing `rejected`. Only `verified`, `cached`, `audited` and `promoted` are **servable**; the delivery gate (`LabStore.get`) returns nothing for the others.
- **Transitions** (a closed table; anything else is refused): `verified -> cached` (served again from the store, after re-verification); `verified|cached -> audited` (an audit passes: the stored source re-verifies under the current checker and verifier, and a stored passage still states the formula); `audited -> promoted` (audited and delivered at least 3 times); any servable `-> evicted` (a flag, or a failed audit); any servable `-> stale` (the template version, the contract fingerprint or the generator identity differs from the current one). `evicted` and `stale` are terminal for that record.
- **A cache path in `compose_lab`:** before calling the generator, look for a servable lab for the contract; re-verify its stored source through the same verifier (so the deliverable type is still minted only by the verifier); on success deliver it and skip the generator call; on failure evict it and fall through to generation.
- **Report-only crystallisation candidates:** contracts with at least 2 promoted labs are listed. Nothing is built from the list.

**Out, with reasons:**

- **Crystallisation into a level 1 component:** a new catalog component needs a written structural precondition that retrieval can satisfy (constraint 7) and the Composer's admission; with one lab per contract today there is no repeated pattern to crystallise. Documented, not built (never build the second of anything).
- **A wire change:** no field is added to `LabList` or `VerifiedLab`; the lifecycle state is server-side. (So no schema-first change.)
- **A model-based audit:** audits are the existing deterministic checks only.
- **A UI for flags:** the flag is a store method; a user-facing control is not in scope.

## Approach

State and rules live in `api/labs/lifecycle.py` (pure, tested); `SqliteLabStore` enforces them (it refuses an illegal transition and migrates an older `labs.db` by adding columns); `compose_lab` uses the cache path. The verifier remains the only minter; the store never returns a type the delivery path accepts.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A cached lab is served without the generator but with a stale evidence passage | Medium | The cache path re-verifies the source and re-checks `find_source`; an audit does the same |
| A migration breaks an existing `labs.db` | Low | Columns are added only if missing; a test opens an old-schema file |
| The cache path weakens the verifier-only mint | High if wrong | The block builder still takes a `VerifiedArtifact`, minted by `verify()` on the stored source; the existing "no path bypasses the verifier" test must stay green |

## Definition of done

A closed transition table with tests for every legal and illegal edge; evicted and stale labs are never delivered (through the validator too); the cache path skips the generator and still verifies; an old `labs.db` opens; the full suite, ruff and pyright are clean; D-41, STATUS, CHANGELOG current.
