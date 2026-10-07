"""LabStore: verified labs behind an abstraction (constraint 6, D-36), and a local SQLite implementation (`labs.db`).

The store holds what the verifier minted and what it refused. `put_verified` takes only a `VerifiedArtifact`, checks that the hash of its
source is the recorded one, that its id is the one its contract and hash give, and that its contract exists, and never replaces a lab (the same
id is the same source). `get` recomputes the hash of the stored source and returns nothing for a row that no longer matches it, so an edited
row is not a lab. The delivery gate (the block validator) re-derives a `VerifiedLab` block from the stored record by `labId`, re-checks the
stored source and compares the contract's fingerprint, so a block whose source differs from the record by one byte, a lab verified for another
contract, and a tampered row are all refused. Rejected sources are kept (state `rejected`, with the stage and the reason, capped in length) as
an audit trail and are never served. Lifecycle states beyond `verified` are P4b.
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from api.labs.contract import CONTRACTS
from api.labs.verifier import Checked, VerifiedArtifact, lab_id_for, source_sha256

MAX_REJECTED_SOURCE_CHARS = 20_000


@dataclass(frozen=True)
class StoredLab:
    """A record, not an artifact: the delivery path never accepts this type."""

    lab_id: str
    contract_id: str
    contract_sha256: str
    source: str
    source_sha256: str
    template_version: int
    checked: Checked
    state: str


class LabStore(ABC):
    @abstractmethod
    def put_verified(self, artifact: VerifiedArtifact) -> StoredLab: ...

    @abstractmethod
    def put_rejected(self, contract_id: str, source: str, stage: str, reason: str) -> None: ...

    @abstractmethod
    def get(self, lab_id: str) -> StoredLab | None:
        """A verified lab by id, or None (a rejected one is never returned, nor a row whose source no longer matches its hash)."""

    @abstractmethod
    def rejected(self) -> list[dict[str, str]]: ...


_COLUMNS = "lab_id, contract_id, contract_sha256, source, source_sha256, template_version, checked, state, reason, created_at"


class SqliteLabStore(LabStore):
    def __init__(self, path: Path):
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS labs (lab_id TEXT PRIMARY KEY, contract_id TEXT NOT NULL, contract_sha256 TEXT NOT NULL, "
                "source TEXT NOT NULL, source_sha256 TEXT NOT NULL, template_version INTEGER NOT NULL, checked TEXT NOT NULL, "
                "state TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def put_verified(self, artifact: VerifiedArtifact) -> StoredLab:
        if not isinstance(artifact, VerifiedArtifact):
            raise TypeError("only a VerifiedArtifact can be stored as verified")
        if source_sha256(artifact.source) != artifact.source_sha256:
            raise ValueError("the artifact's source does not match its hash")
        if artifact.contract_id not in CONTRACTS:
            raise ValueError("the artifact's contract is unknown")
        if artifact.lab_id != lab_id_for(artifact.contract_id, artifact.source_sha256):
            raise ValueError("the artifact's id is not the one its contract and source give")
        checked = {
            "reference_cases": artifact.checked.reference_cases,
            "properties": artifact.checked.properties,
            "fuzz_cases": artifact.checked.fuzz_cases,
            "grid_points": artifact.checked.grid_points,
        }
        with closing(self._connect()) as db, db:
            # OR IGNORE: the same id is the same source and contract, and a stored lab is never replaced
            db.execute(
                f"INSERT OR IGNORE INTO labs ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, 'verified', NULL, ?)",
                (
                    artifact.lab_id,
                    artifact.contract_id,
                    artifact.contract_sha256,
                    artifact.source,
                    artifact.source_sha256,
                    artifact.template_version,
                    json.dumps(checked),
                    datetime.now(UTC).isoformat(),
                ),
            )
        stored = self.get(artifact.lab_id)
        if stored is None:
            raise ValueError("the lab could not be stored")
        return stored

    def put_rejected(self, contract_id: str, source: str, stage: str, reason: str) -> None:
        sha = source_sha256(source)
        source = source[
            :MAX_REJECTED_SOURCE_CHARS
        ]  # an untrusted source is kept for audit, not without limit
        with closing(self._connect()) as db, db:
            db.execute(
                f"INSERT OR IGNORE INTO labs ({_COLUMNS}) VALUES (?, ?, '', ?, ?, 0, '{{}}', 'rejected', ?, ?)",
                (
                    f"rejected-{sha[:16]}",
                    contract_id,
                    source,
                    sha,
                    f"{stage}: {reason}"[:300],
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get(self, lab_id: str) -> StoredLab | None:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT lab_id, contract_id, contract_sha256, source, source_sha256, template_version, checked, state FROM labs "
                "WHERE lab_id = ? AND state = 'verified'",
                (lab_id,),
            ).fetchone()
        if row is None:
            return None
        if source_sha256(row[3]) != row[4] or row[0] != lab_id_for(row[1], row[4]):
            return None  # an edited row is not a lab
        c = json.loads(row[6])
        checked = Checked(c["reference_cases"], c["properties"], c["fuzz_cases"], c["grid_points"])
        return StoredLab(row[0], row[1], row[2], row[3], row[4], int(row[5]), checked, row[7])

    def rejected(self) -> list[dict[str, str]]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT contract_id, source_sha256, reason FROM labs WHERE state = 'rejected' ORDER BY created_at"
            ).fetchall()
        return [{"contract_id": r[0], "source_sha256": r[1], "reason": r[2]} for r in rows]
