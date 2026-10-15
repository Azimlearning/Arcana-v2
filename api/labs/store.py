"""LabStore: verified labs behind an abstraction (constraint 6, D-36), and a local SQLite implementation (`labs.db`).

The store holds what the verifier minted and what it refused. `put_verified` takes only a `VerifiedArtifact`, checks that the hash of its
source is the recorded one, that its id is the one its contract and hash give, and that its contract exists, and never replaces a lab (the same
id is the same source). `get` recomputes the hash of the stored source and returns nothing for a row that no longer matches it, so an edited
row is not a lab. The delivery gate (the block validator) re-derives a `VerifiedLab` block from the stored record by `labId`, re-checks the
stored source and compares the contract's fingerprint, so a block whose source differs from the record by one byte, a lab verified for another
contract, and a tampered row are all refused. Rejected sources are kept (state `rejected`, with the stage and the reason, capped in length) as
an audit trail and are never served. The lifecycle (D-41, `api/labs/lifecycle.py`): only `verified`, `cached`, `audited` and `promoted` labs are
served; `evicted` and `stale` are not, and a transition outside the closed table is refused.
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
from api.labs.lifecycle import (
    CRYSTALLISATION_MIN_PROMOTED,
    PROMOTE_AFTER_DELIVERIES,
    SERVABLE,
    can_transition,
)
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
    def put_verified(self, artifact: VerifiedArtifact, generator_id: str = "") -> StoredLab: ...

    @abstractmethod
    def put_rejected(self, contract_id: str, source: str, stage: str, reason: str) -> None: ...

    @abstractmethod
    def get(self, lab_id: str) -> StoredLab | None:
        """A verified lab by id, or None (a rejected one is never returned, nor a row whose source no longer matches its hash)."""

    @abstractmethod
    def rejected(self) -> list[dict[str, str]]: ...

    @abstractmethod
    def find_servable(self, contract_id: str) -> StoredLab | None:
        """The newest servable lab for a contract (a candidate for reuse), or None."""

    @abstractmethod
    def transition(self, lab_id: str, target: str, reason: str) -> None:
        """Move a lab along the closed table in `api/labs/lifecycle.py`; an illegal move raises `ValueError`."""

    @abstractmethod
    def flag(self, lab_id: str, reason: str) -> None:
        """Evict a servable lab (a flag, or a failed audit). It is kept as a record and never served again."""

    @abstractmethod
    def record_delivery(self, lab_id: str) -> None:
        """Count one delivery; a lab audited and delivered enough times is promoted."""

    @abstractmethod
    def mark_stale(self, template_version: int, contract_sha256s: dict[str, str], generator_id: str) -> int:
        """Mark servable labs made under another template, contract fingerprint or generator as stale; returns how many."""

    @abstractmethod
    def counts(self) -> dict[str, int]: ...

    @abstractmethod
    def crystallisation_candidates(self) -> list[str]:
        """Contracts with enough promoted labs to be proposed for crystallisation (report only: nothing is built from it)."""


_COLUMNS = "lab_id, contract_id, contract_sha256, source, source_sha256, template_version, checked, state, reason, created_at"
_SERVABLE_SQL = ", ".join(f"'{state}'" for state in sorted(SERVABLE))


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
            have = {row[1] for row in db.execute("PRAGMA table_info(labs)")}
            for column, ddl in (  # an older labs.db gains the lifecycle columns; existing rows keep their state
                ("deliveries", "INTEGER NOT NULL DEFAULT 0"),
                ("audits", "INTEGER NOT NULL DEFAULT 0"),
                ("generator_id", "TEXT NOT NULL DEFAULT ''"),
                ("updated_at", "TEXT"),
            ):
                if column not in have:
                    db.execute(f"ALTER TABLE labs ADD COLUMN {column} {ddl}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def put_verified(self, artifact: VerifiedArtifact, generator_id: str = "") -> StoredLab:
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
                f"INSERT OR IGNORE INTO labs ({_COLUMNS}, generator_id) VALUES (?, ?, ?, ?, ?, ?, ?, 'verified', NULL, ?, ?)",
                (
                    artifact.lab_id,
                    artifact.contract_id,
                    artifact.contract_sha256,
                    artifact.source,
                    artifact.source_sha256,
                    artifact.template_version,
                    json.dumps(checked),
                    datetime.now(UTC).isoformat(),
                    generator_id,
                ),
            )
        if self._state(artifact.lab_id) == "stale":  # verified again just now, under the current template and contract
            with closing(self._connect()) as db, db:
                db.execute(
                    "UPDATE labs SET state = 'verified', reason = 'revalidated', contract_sha256 = ?, template_version = ?, checked = ?, "
                    "generator_id = ?, deliveries = 0, updated_at = ? WHERE lab_id = ? AND state = 'stale' AND source_sha256 = ?",
                    (
                        artifact.contract_sha256,
                        artifact.template_version,
                        json.dumps(checked),
                        generator_id,
                        datetime.now(UTC).isoformat(),
                        artifact.lab_id,
                        artifact.source_sha256,
                    ),
                )
        stored = self.get(artifact.lab_id)
        if stored is None:
            raise ValueError("the lab could not be stored (an evicted lab is not stored again)")
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
                f"WHERE lab_id = ? AND state IN ({_SERVABLE_SQL})",
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

    def _state(self, lab_id: str) -> str | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT state FROM labs WHERE lab_id = ?", (lab_id,)).fetchone()
        return None if row is None else str(row[0])

    def find_servable(self, contract_id: str) -> StoredLab | None:
        with closing(self._connect()) as db:
            rows = db.execute(
                f"SELECT lab_id FROM labs WHERE contract_id = ? AND state IN ({_SERVABLE_SQL}) ORDER BY created_at DESC",
                (contract_id,),
            ).fetchall()
        for (lab_id,) in rows:
            found = self.get(lab_id)  # get() re-checks the hash: an edited row is skipped, not served
            if found is not None:
                return found
        return None

    def transition(self, lab_id: str, target: str, reason: str) -> None:
        current = self._state(lab_id)
        if current is None:
            raise ValueError(f"no lab {lab_id!r}")
        if not can_transition(current, target):
            raise ValueError(f"a {current} lab cannot become {target}")
        audits = ", audits = audits + 1" if target == "audited" else ""
        with closing(self._connect()) as db, db:
            db.execute(
                f"UPDATE labs SET state = ?, reason = ?, updated_at = ?{audits} WHERE lab_id = ? AND state = ?",
                (target, reason[:200], datetime.now(UTC).isoformat(), lab_id, current),
            )

    def flag(self, lab_id: str, reason: str) -> None:
        if self._state(lab_id) == "evicted":
            return  # already evicted (two requests failing at once): nothing more to record
        self.transition(lab_id, "evicted", reason)

    def record_delivery(self, lab_id: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                f"UPDATE labs SET deliveries = deliveries + 1, updated_at = ? WHERE lab_id = ? AND state IN ({_SERVABLE_SQL})",
                (datetime.now(UTC).isoformat(), lab_id),
            )
            row = db.execute("SELECT state, deliveries FROM labs WHERE lab_id = ?", (lab_id,)).fetchone()
        if row and row[0] == "audited" and int(row[1]) >= PROMOTE_AFTER_DELIVERIES:
            self.transition(lab_id, "promoted", f"audited and delivered {row[1]} times")

    def mark_stale(self, template_version: int, contract_sha256s: dict[str, str], generator_id: str) -> int:
        with closing(self._connect()) as db:
            rows = db.execute(
                f"SELECT lab_id, contract_id, contract_sha256, template_version, generator_id FROM labs WHERE state IN ({_SERVABLE_SQL})"
            ).fetchall()
        marked = 0
        for lab_id, contract_id, fingerprint, version, made_by in rows:
            reasons = []
            if int(version) != template_version:
                reasons.append("template version changed")
            if contract_sha256s.get(contract_id) != fingerprint:
                reasons.append("contract changed")
            if made_by and generator_id and made_by != generator_id:
                reasons.append("generator changed")
            if reasons:
                self.transition(lab_id, "stale", "; ".join(reasons))
                marked += 1
        return marked

    def counts(self) -> dict[str, int]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT state, COUNT(*) FROM labs GROUP BY state").fetchall()
        return {str(state): int(n) for state, n in rows}

    def crystallisation_candidates(self) -> list[str]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT contract_id, COUNT(*) FROM labs WHERE state = 'promoted' GROUP BY contract_id HAVING COUNT(*) >= ? ORDER BY 1",
                (CRYSTALLISATION_MIN_PROMOTED,),
            ).fetchall()
        return [str(r[0]) for r in rows]
