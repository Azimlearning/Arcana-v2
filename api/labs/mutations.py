"""The VerifiedLab mutation suite (P4 V7, D-36): run every planted defect through the real stages and record whether the right stage refused it.

Three families, each through the stage that must catch it:
- **static** (`planted.STATIC_DEFECTS`): the checker must refuse the source and name the rule;
- **execution** (`planted_runtime.EXECUTION_DEFECTS`): the source passes the checker and the verifier must refuse it at the named stage;
- **tampering** (`planted_runtime.FORGERIES`): a verified lab's block is changed in one way; the delivery gate (`validate_block`) must refuse it.

`run_suite` returns one `Outcome` per defect; `summary` turns them into the detection rate per class and overall. A defect counts as detected
only if it was refused by the stage and rule it names: refused by the wrong stage is reported as a miss, because it means the named defence did
not hold. The set is the planted set, not all possible attacks.
"""

from __future__ import annotations

import copy
import hashlib
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from api.agents.compose import compose_lab
from api.core.errors import ValidationFailed
from api.genui.validate import validate_block
from api.labs.checker import check_source
from api.labs.contract import ranknet_contract
from api.labs.generator import FakeLabGenerator
from api.labs.planted import STATIC_DEFECTS
from api.labs.planted_runtime import EXECUTION_DEFECTS, FORGERIES
from api.labs.store import SqliteLabStore
from api.labs.verifier import VerificationFailed, lab_id_for, verify
from api.stores.doc_store import Chunk, Document
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine

PASSAGE = (
    "RankNet is a pairwise loss that measures the correctness of relative passage orders: "
    "L = sum_i sum_j 1[r_i < r_j] log(1 + exp(s_j - s_i))."
)


@dataclass(frozen=True)
class Outcome:
    family: str
    kind: str
    name: str
    expected: str
    """The rule, stage or gate that must refuse it."""
    refused_by: str | None
    detected: bool


def _static() -> list[Outcome]:
    out = []
    names = [p.name for p in ranknet_contract().parameters]
    for d in STATIC_DEFECTS:
        result = check_source(d.source, names)
        by = ",".join(result.rules) if not result.ok else None
        out.append(Outcome("static", d.kind, d.name, d.rule, by, d.rule in result.rules))
    return out


def _execution() -> list[Outcome]:
    out = []
    contract = ranknet_contract()
    for d in EXECUTION_DEFECTS:
        try:
            verify(contract, d.source)
            out.append(Outcome("execution", d.kind, d.name, d.stage, None, False))
        except VerificationFailed as failed:
            out.append(
                Outcome("execution", d.kind, d.name, d.stage, failed.stage, failed.stage == d.stage)
            )
    return out


def _tampering() -> list[Outcome]:
    out = []
    contract = ranknet_contract()
    with tempfile.TemporaryDirectory(
        ignore_cleanup_errors=True
    ) as tmp:  # Windows keeps the SQLite file open a moment longer
        docs = SqliteDocStore(make_engine(Path(tmp) / "docs.db"))
        docs.put_document(
            Document("d1", "A Ranking Paper", "d1.pdf", "ready", 1, None, "2026-10-08")
        )
        docs.put_chunks([Chunk("c1", "d1", 0, 16, PASSAGE)])
        labs = SqliteLabStore(Path(tmp) / "labs.db")
        # the unforged block comes out of the one path that makes blocks, so the gate is shown not to be simply refusing everything
        _, blocks = compose_lab(docs, labs, FakeLabGenerator(), contract.id)
        genuine = blocks[0].model_dump()
        assert genuine["meta"]["status"] == "ready"
        for name, forge in FORGERIES.items():
            raw = copy.deepcopy(genuine)
            forge(raw["data"])
            try:
                validate_block(raw, docs, labs=labs)
                out.append(Outcome("tampering", "forgery", name, "delivery gate", None, False))
            except ValidationFailed:
                out.append(
                    Outcome("tampering", "forgery", name, "delivery gate", "delivery gate", True)
                )
    return out


def _row_tampering() -> list[Outcome]:
    """Someone with write access to `labs.db` edits a verified row (and, in the cases that matter, the block to match it): the gate must still refuse."""
    evil = "function lab(p) { return 1000; }"
    failing = 'function lab(p) { return fetch("x"); }'

    def sha(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    # name -> (the SQL to run on the row, its parameters, the changes to make to the block so that it equals the edited row)
    new_id = lab_id_for("ranknet_pairwise_loss", sha(failing))
    cases: dict[str, tuple[str, dict[str, Any], dict[str, Any]]] = {
        "row_source_and_hash_edited": (
            "UPDATE labs SET source = :evil, source_sha256 = :evil_sha WHERE lab_id = :id",
            {"evil": evil, "evil_sha": sha(evil)},
            {"source": evil, "sourceSha256": sha(evil)},
        ),
        "row_source_only_edited": (
            "UPDATE labs SET source = :evil WHERE lab_id = :id",
            {"evil": evil},
            {"source": evil},
        ),
        "row_contract_fingerprint_edited": (
            "UPDATE labs SET contract_sha256 = :zero WHERE lab_id = :id",
            {"zero": "0" * 64},
            {},
        ),
        "row_template_version_edited": (
            "UPDATE labs SET template_version = 3 WHERE lab_id = :id",
            {},
            {"templateVersion": 3},
        ),
        "row_id_no_longer_matches_hash": (
            "UPDATE labs SET lab_id = 'ranknet_pairwise_loss-aaaaaaaaaaaa' WHERE lab_id = :id",
            {},
            {"labId": "ranknet_pairwise_loss-aaaaaaaaaaaa"},
        ),
        "row_replaced_by_consistent_but_failing_source": (
            "UPDATE labs SET lab_id = :new_id, source = :src, source_sha256 = :src_sha WHERE lab_id = :id",
            {"new_id": new_id, "src": failing, "src_sha": sha(failing)},
            {"labId": new_id, "source": failing, "sourceSha256": sha(failing)},
        ),
    }
    out = []
    for name, (sql, params, block_changes) in cases.items():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            docs = SqliteDocStore(make_engine(Path(tmp) / "docs.db"))
            docs.put_document(
                Document("d1", "A Ranking Paper", "d1.pdf", "ready", 1, None, "2026-10-08")
            )
            docs.put_chunks([Chunk("c1", "d1", 0, 16, PASSAGE)])
            db_path = Path(tmp) / "labs.db"
            labs = SqliteLabStore(db_path)
            _, blocks = compose_lab(docs, labs, FakeLabGenerator(), "ranknet_pairwise_loss")
            genuine = blocks[0].model_dump()
            with closing(sqlite3.connect(db_path)) as db, db:
                db.execute(sql, {**params, "id": genuine["data"]["labId"]})
            raw = copy.deepcopy(genuine)
            raw["data"].update(block_changes)
            try:
                validate_block(raw, docs, labs=labs)
                out.append(Outcome("row_tampering", "labs.db", name, "delivery gate", None, False))
            except ValidationFailed:
                out.append(
                    Outcome(
                        "row_tampering", "labs.db", name, "delivery gate", "delivery gate", True
                    )
                )
    return out


def run_suite() -> list[Outcome]:
    return [*_static(), *_execution(), *_tampering(), *_row_tampering()]


def summary(outcomes: list[Outcome]) -> dict[str, Any]:
    def rate(rows: list[Outcome]) -> dict[str, Any]:
        hit = sum(1 for o in rows if o.detected)
        return {"planted": len(rows), "detected": hit, "rate": hit / len(rows) if rows else None}

    by_family: dict[str, list[Outcome]] = {}
    by_kind: dict[str, list[Outcome]] = {}
    for o in outcomes:
        by_family.setdefault(o.family, []).append(o)
        by_kind.setdefault(f"{o.family}/{o.kind}", []).append(o)
    return {
        "overall": rate(outcomes),
        "by_family": {k: rate(v) for k, v in sorted(by_family.items())},
        "by_class": {k: rate(v) for k, v in sorted(by_kind.items())},
        "missed": [asdict(o) for o in outcomes if not o.detected],
    }
