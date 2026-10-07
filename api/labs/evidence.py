"""The evidence of a lab and its block data (P4 V4, D-36).

`find_source` is the lab's evidence precondition (constraint 7): a stored passage must hold the sentence that states the formula. Without it
the lab is not made. `derive_lab_data` is the block's `data` as a pure function of a verified record (or a freshly minted artifact), the
contract and that citation: the Composer builds the block from it and the validator derives it again from the stored record and requires
equality, so the two cannot drift.
"""

from __future__ import annotations

from typing import Any

from api.genui.text import normalise
from api.labs.contract import LabContract
from api.labs.store import StoredLab
from api.labs.verifier import VerifiedArtifact
from api.stores.doc_store import DocStore

BLANK_LAB_DATA: dict[str, Any] = {
    "labId": "",
    "contractId": "",
    "title": "",
    "parameters": [],
    "sweep": "",
    "gridSteps": 0,
    "outputLabel": "",
    "source": "",
    "sourceSha256": "",
    "templateVersion": 0,
    "citations": [],
    "checked": {"referenceCases": 0, "properties": 0, "fuzzCases": 0, "gridPoints": 0},
}
"""A placeholder lab carries nothing. One constant, used by the builder and the validator, so they cannot drift."""


def find_source(docs: DocStore, contract: LabContract) -> dict[str, Any] | None:
    """The citation (id `c1`) of the first stored passage, in reading order, whose whitespace-normalised text holds the contract's source phrase
    verbatim, or None."""
    phrase = normalise(contract.source_phrase)
    for chunk in sorted(docs.all_chunks(), key=lambda c: (c.doc_id, c.ordinal)):
        if phrase in normalise(chunk.text):
            document = docs.get_document(chunk.doc_id)
            return {
                "id": "c1",
                "chunkId": chunk.id,
                "docId": chunk.doc_id,
                "docTitle": document.title if document else "",
                "page": chunk.page,
                "quote": phrase,
            }
    return None


def derive_lab_data(
    lab: VerifiedArtifact | StoredLab, contract: LabContract, citation: dict[str, Any]
) -> dict[str, Any]:
    """The exact `data` of a ready `VerifiedLab` block."""
    return {
        "labId": lab.lab_id,
        "contractId": contract.id,
        "title": contract.title,
        "parameters": [
            {
                "name": p.name,
                "label": p.label,
                "min": p.min,
                "max": p.max,
                "default": p.default,
                "unit": p.unit,
            }
            for p in contract.parameters
        ],
        "sweep": contract.sweep,
        "gridSteps": contract.grid,
        "outputLabel": contract.output_label,
        "source": lab.source,
        "sourceSha256": lab.source_sha256,
        "templateVersion": lab.template_version,
        "citations": [citation],
        "checked": {
            "referenceCases": lab.checked.reference_cases,
            "properties": lab.checked.properties,
            "fuzzCases": lab.checked.fuzz_cases,
            "gridPoints": lab.checked.grid_points,
        },
    }
