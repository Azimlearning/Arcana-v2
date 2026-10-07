"""LabStore: verified labs behind an abstraction (constraint 6, D-36), and a local SQLite implementation (`labs.db`).

The store holds what the verifier minted and what it refused. `put_verified` takes only a `VerifiedArtifact` and checks that the hash of
its source is the recorded one; the delivery gate (the block validator) re-derives a `VerifiedLab` block from the stored record by
`labId`, so a block whose source differs from the record by one byte is refused. Rejected sources are kept (state `rejected`, with the
stage and the reason) as an audit trail and are never served. Lifecycle states beyond `verified` are P4b.
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from api.labs.verifier import Checked, VerifiedArtifact, source_sha256


@dataclass(frozen=True)
class StoredLab:
    """A record, not an artifact: the delivery path never accepts this type."""

    lab_id: str
    contract_id: str
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
        """A verified lab by id, or None (a rejected one is never returned)."""

    @abstractmethod
    def rejected(self) -> list[dict[str, str]]: ...


_COLUMNS = "lab_id, contract_id, source, source_sha256, template_version, checked, state, reason, created_at"


class SqliteLabStore(LabStore):
    def __init__(self, path: Path):
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS labs (lab_id TEXT PRIMARY KEY, contract_id TEXT NOT NULL, source TEXT NOT NULL, "
                "source_sha256 TEXT NOT NULL, template_version INTEGER NOT NULL, checked TEXT NOT NULL, state TEXT NOT NULL, "
                "reason TEXT, created_at TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def put_verified(self, artifact: VerifiedArtifact) -> StoredLab:
        if not isinstance(artifact, VerifiedArtifact):
            raise TypeError("only a VerifiedArtifact can be stored as verified")
        if source_sha256(artifact.source) != artifact.source_sha256:
            raise ValueError("the artifact's source does not match its hash")
        checked = {
            "reference_cases": artifact.checked.reference_cases,
            "properties": artifact.checked.properties,
            "fuzz_cases": artifact.checked.fuzz_cases,
        }
        with closing(self._connect()) as db, db:
            db.execute(
                f"INSERT OR REPLACE INTO labs ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, 'verified', NULL, ?)",
                (
                    artifact.lab_id,
                    artifact.contract_id,
                    artifact.source,
                    artifact.source_sha256,
                    artifact.template_version,
                    json.dumps(checked),
                    datetime.now(UTC).isoformat(),
                ),
            )
        stored = self.get(artifact.lab_id)
        assert stored is not None
        return stored

    def put_rejected(self, contract_id: str, source: str, stage: str, reason: str) -> None:
        sha = source_sha256(source)
        with closing(self._connect()) as db, db:
            db.execute(
                f"INSERT OR IGNORE INTO labs ({_COLUMNS}) VALUES (?, ?, ?, ?, 0, '{{}}', 'rejected', ?, ?)",
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
                "SELECT lab_id, contract_id, source, source_sha256, template_version, checked, state FROM labs "
                "WHERE lab_id = ? AND state = 'verified'",
                (lab_id,),
            ).fetchone()
        if row is None:
            return None
        c = json.loads(row[5])
        checked = Checked(c["reference_cases"], c["properties"], c["fuzz_cases"])
        return StoredLab(row[0], row[1], row[2], row[3], int(row[4]), checked, row[6])

    def rejected(self) -> list[dict[str, str]]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT contract_id, source_sha256, reason FROM labs WHERE state = 'rejected' ORDER BY created_at"
            ).fetchall()
        return [{"contract_id": r[0], "source_sha256": r[1], "reason": r[2]} for r in rows]
