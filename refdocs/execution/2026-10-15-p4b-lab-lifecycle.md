# Execution: P4b-lite, the governed lifecycle for verified labs (D-41)

> Plan: `refdocs/plans/2026-10-15-p4b-lab-lifecycle.md`. Status: **Built (2026-10-15)**: L1 to L4 done; D-41. One deviation from the task text: the audit lives in `api/labs/audit.py`, not `lifecycle.py` (a circular import with the store), and a `stale` lab can be revalidated (stale to verified) by re-verification, which the plan had as terminal.

### Task L1: the state table (`api/labs/lifecycle.py`)

States, `SERVABLE`, the closed `ALLOWED` transition table, `PROMOTE_AFTER_DELIVERIES = 3`, `CRYSTALLISATION_MIN_PROMOTED = 2`, and `can_transition`. **Verify:** a test over the full table (every legal edge allowed, every other pair refused, terminal states have no exits).

### Task L2: the store (`api/labs/store.py`)

New columns `deliveries`, `audits`, `generator_id`, `state_reason`, `updated_at` added if missing; `get` returns servable states only; `find_servable(contract_id)`, `transition`, `record_delivery`, `flag`, `mark_stale`, `counts`, `crystallisation_candidates`. The generator interface gets `generator_id`. **Verify:** tests for each method, an old-schema database opens, an illegal transition raises, evicted and stale labs are not returned by `get`.

### Task L3: the cache path and the audit (`api/agents/compose.py`, `api/labs/lifecycle.py`)

`compose_lab` looks for a servable lab, re-verifies its stored source, delivers it and skips the generator; a failure evicts it. `audit_lab` re-verifies and re-checks the evidence, moving the lab to `audited` or `evicted`. **Verify:** a counting generator is not called on the second request for a contract; a lab whose stored source stopped verifying is evicted and regenerated; the existing tests that no path bypasses the verifier stay green.

### Task L4: docs and review

D-41, STATUS, CHANGELOG, the execution doc; `schema-guardian` over the delivery path (read-only); the full suite.
