"""The governed lifecycle of a stored lab (P4b-lite, D-41, PRD §3): the states and the closed transition table.

    verified -> cached -> audited -> promoted        (servable states)
    any servable -> evicted                          (a flag, or a failed audit)
    any servable -> stale                            (the template, the contract or the generator is no longer the one that made it)
    stale -> verified                                (the stored source verifies again under the current template: revalidated)

`generated` is the transient state before the verifier and is never stored; `rejected` is the verifier's refusal and is never served. Only
the four servable states are delivered. The table below is closed: a transition not in it is refused, `evicted` has no exit and a `stale` lab
can only be re-verified (back to `verified`) or evicted, and nothing here can mint a deliverable type (only `verify()` can). An audit
(`api/labs/audit.py`) re-runs the verifier on the stored source and re-checks that a stored passage still states the formula, so a lab is not
kept on the strength of a check made long ago.
"""

SERVABLE = frozenset({"verified", "cached", "audited", "promoted"})
TERMINAL = frozenset({"evicted", "rejected"})
ALLOWED: dict[str, frozenset[str]] = {
    "verified": frozenset({"cached", "audited", "evicted", "stale"}),
    "cached": frozenset({"audited", "evicted", "stale"}),
    "audited": frozenset({"promoted", "evicted", "stale"}),
    "promoted": frozenset({"evicted", "stale"}),
    "stale": frozenset({"verified", "evicted"}),  # re-verified under the current template, or flagged: never served while stale
    "evicted": frozenset(),
    "rejected": frozenset(),
}
# A verifier failure at one of these stages can be the machine (a timeout under load, a crashed runner), not the lab: it is never a reason to
# evict a stored lab, only to decline to serve it this time. Every other stage is deterministic, so a failure there is the lab's.
TRANSIENT_STAGES = frozenset({"run"})
PROMOTE_AFTER_DELIVERIES = 3
CRYSTALLISATION_MIN_PROMOTED = 2


def can_transition(source: str, target: str) -> bool:
    return target in ALLOWED.get(source, frozenset())
