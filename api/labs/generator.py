"""LabGenerator: where a lab's function comes from (P4 V5, D-36), behind an interface (constraint 6).

A generator turns a contract into the source text of one function. It is **untrusted by construction**: whatever it returns goes through
the checker and the verifier, and nothing it returns reaches the client except as a `VerifiedArtifact`. The fake is deterministic and free
(it returns a hand-written function for each known contract, or a configured one, so tests can feed it good and defective sources); the
live generator goes through the LLM seam and the spend ledger and is built in V9, after Azim confirms an amount.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from api.labs.contract import LabContract

RANKNET_SOURCE = """function lab(p) {
  const d = p.sj - p.si;
  if (d > 0) {
    return d + Math.log1p(Math.exp(-d));
  }
  return Math.log1p(Math.exp(d));
}"""
"""A correct RankNet pairwise loss, written without overflow (the formula the cited passage states)."""


F1_AT_K_SOURCE = """function lab(p) {
  const h = Math.min(p.hits, p.k, p.relevant);
  if (h <= 0) {
    return 0;
  }
  const precision = h / p.k;
  const recall = h / p.relevant;
  return 2 * precision * recall / (precision + recall);
}"""

INFONCE_SOURCE = """function lab(p) {
  return -Math.log(p.phi_pos / (p.phi_pos + p.negatives * p.phi_neg));
}"""

COSINE_DISTANCE_SOURCE = """function lab(p) {
  const c = Math.cos(p.angle * Math.PI / 180);
  return 1 - Math.max(c, 0);
}"""


class LabGenerator(ABC):
    generator_id: str = "unknown"
    """Which generator (and prompt) made a source; a stored lab whose id differs from the current one is marked stale (P4b, D-41)."""

    @abstractmethod
    def generate(self, contract: LabContract) -> str:
        """The source text of `lab(p)` for `contract`. Untrusted: the caller checks and verifies it."""


class FakeLabGenerator(LabGenerator):
    """Deterministic and free: a known function per contract, or `overrides[contract id]` (a defective one, in a test)."""

    generator_id = "fake-lab-1"

    def __init__(self, overrides: dict[str, str] | None = None):
        self._known = {
            "ranknet_pairwise_loss": RANKNET_SOURCE,
            "f1_at_k": F1_AT_K_SOURCE,
            "infonce_loss": INFONCE_SOURCE,
            "cosine_chunk_distance": COSINE_DISTANCE_SOURCE,
        }
        self._overrides = dict(overrides or {})
        self.calls: list[str] = []

    def generate(self, contract: LabContract) -> str:
        self.calls.append(contract.id)
        if contract.id in self._overrides:
            return self._overrides[contract.id]
        if contract.id not in self._known:
            raise KeyError(f"the fake generator has no function for {contract.id!r}")
        return self._known[contract.id]
