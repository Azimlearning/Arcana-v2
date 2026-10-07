"""JsonVaultStore: the vault as one JSON file beside the other stores (`<data dir>/vault.json`)."""

from __future__ import annotations

import json
from pathlib import Path

from api.vault.store import VaultStore
from api.vault.types import Vault


class JsonVaultStore(VaultStore):
    def __init__(self, path: Path):
        self._path = path
        self._vault: Vault | None = None
        self._vectors: dict[str, list[float]] = {}
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._vault = Vault.from_dict(raw["vault"])
            self._vectors = {k: list(v) for k, v in raw.get("label_vectors", {}).items()}

    def vault(self) -> Vault | None:
        return self._vault

    def put_vault(self, vault: Vault) -> None:
        self._vault = vault
        self._vectors = {k: v for k, v in self._vectors.items() if k in vault.pages}

    def label_vectors(self) -> dict[str, list[float]]:
        return dict(self._vectors)

    def put_label_vectors(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = {k: list(v) for k, v in vectors.items()}

    def save(self) -> None:
        if self._vault is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        body = {"vault": self._vault.to_dict(), "label_vectors": self._vectors}
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
        tmp.replace(self._path)
