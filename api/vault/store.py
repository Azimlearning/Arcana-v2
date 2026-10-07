"""VaultStore: the compiled vault behind an abstraction (constraint 6, D-09, D-35).

Code calls this interface, never a file or a database directly. The vault is a derived layer: it is rebuilt from the graph
and the passages, so a store holds a build and the vectors of the page labels (for the semantic resolution step), nothing
that cannot be recomputed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from api.vault.types import Vault


class VaultStore(ABC):
    @abstractmethod
    def vault(self) -> Vault | None:
        """The stored vault, or None if none has been built."""

    @abstractmethod
    def put_vault(self, vault: Vault) -> None:
        """Replace the stored vault (and drop label vectors that no longer match its pages)."""

    @abstractmethod
    def label_vectors(self) -> dict[str, list[float]]:
        """Page id to the embedding of its display label, for the pages that have one."""

    @abstractmethod
    def label_meta(self) -> dict[str, object]:
        """Where the label vectors came from: `mode` (fake or live), `model`, `dim` and `labels_sha256` (a hash of the page ids
        and labels they were made for). Empty if there are no vectors. A comparison refuses vectors whose provenance does not
        match the run (fake vectors compared with live question embeddings are meaningless)."""

    @abstractmethod
    def put_label_vectors(
        self, vectors: dict[str, list[float]], meta: dict[str, object]
    ) -> None: ...

    @abstractmethod
    def save(self) -> None:
        """Persist. A reopened store reads back the same vault."""
