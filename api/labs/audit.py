"""The audit of a stored lab (P4b-lite, D-41): re-verify its source under the current checker and verifier, and re-check that a stored passage
still states the formula. Pass: a `verified` or `cached` lab becomes `audited`. Fail: the lab is evicted, with the reason kept. If the verifier
tool is unavailable there is no verdict and no change. This is deterministic and makes no model call."""

from __future__ import annotations

from api.labs.checker import LabToolError
from api.labs.contract import CONTRACTS
from api.labs.evidence import find_source
from api.labs.lifecycle import TRANSIENT_STAGES
from api.labs.store import LabStore
from api.labs.verifier import TEMPLATE_VERSION, VerificationFailed, contract_sha256, verify
from api.stores.doc_store import DocStore


def audit_lab(store: LabStore, docs: DocStore, lab_id: str) -> str:
    """Returns the lab's state after the audit, or `missing` when it is not a servable lab."""
    record = store.get(lab_id)
    if record is None:
        return "missing"
    make = CONTRACTS.get(record.contract_id)
    if make is None:
        store.flag(lab_id, "audit: the contract no longer exists")
        return "evicted"
    contract = make()
    if find_source(docs, contract) is None:
        store.flag(lab_id, "audit: no stored passage states the formula any more")
        return "evicted"
    try:
        minted = verify(contract, record.source)
    except VerificationFailed as failed:
        if failed.stage in TRANSIENT_STAGES:
            return record.state  # the machine, not the lab: no verdict, no change
        store.flag(lab_id, f"audit: {failed.stage}: {failed.reason}"[:200])
        return "evicted"
    except LabToolError:
        return record.state
    if (
        record.contract_sha256 != contract_sha256(contract)
        or record.template_version != TEMPLATE_VERSION
        or minted.lab_id != record.lab_id
    ):  # the lab verifies, but not as the record that was stored: it is stale, not audited
        store.transition(lab_id, "stale", "audit: the record is not the current template or contract")
        return "stale"
    if record.state in ("verified", "cached"):
        store.transition(lab_id, "audited", "audit passed")
        return "audited"
    return record.state
