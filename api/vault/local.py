"""JsonVaultStore: the vault as one JSON file beside the other stores (`<data dir>/vault.json`)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from api.vault.store import VaultStore
from api.vault.types import Vault


class JsonVaultStore(VaultStore):
    def __init__(self, path: Path):
        self._path = path
        self._vault: Vault | None = None
        self._vectors: dict[str, list[float]] = {}
        self._meta: dict[str, object] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                vault = Vault.from_dict(raw["vault"])
                vectors = {k: list(v) for k, v in raw.get("label_vectors", {}).items()}
                meta = dict(raw.get("label_meta", {}))
            except (ValueError, KeyError, TypeError):
                # The vault is derived and can always be compiled again: a damaged file is no vault, not a start-up failure.
                return
            self._vault, self._vectors, self._meta = vault, vectors, meta

    def vault(self) -> Vault | None:
        return self._vault

    def put_vault(self, vault: Vault) -> None:
        self._vault = vault
        self._vectors = {k: v for k, v in self._vectors.items() if k in vault.pages}
        if not self._vectors:
            self._meta = {}

    def label_vectors(self) -> dict[str, list[float]]:
        return dict(self._vectors)

    def label_meta(self) -> dict[str, object]:
        return dict(self._meta)

    def put_label_vectors(self, vectors: dict[str, list[float]], meta: dict[str, object]) -> None:
        self._vectors = {k: list(v) for k, v in vectors.items()}
        self._meta = dict(meta)

    def save(self) -> None:
        if self._vault is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "vault": self._vault.to_dict(),
            "label_vectors": self._vectors,
            "label_meta": self._meta,
        }
        tmp = self._path.with_name(f"{self._path.name}.{uuid.uuid4().hex}.tmp")  # no other writer shares this name
        tmp.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
        tmp.replace(self._path)
