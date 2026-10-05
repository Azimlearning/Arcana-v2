"""Exact cosine VectorStore on a normalised numpy matrix, persisted as an .npz (D-09, Q-02).

Chosen by the P0 spike (scripts/vector_store_spike.py; ADR D-17): at this project's scale (a
single-user corpus of at most tens of thousands of chunks) exact search takes milliseconds, needs no
extra dependency, and removes approximate-index error from the graph-vs-flat comparison. The
VectorStore interface keeps a swap to an indexed store cheap if the corpus ever outgrows it.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from api.stores.vector_store import VectorHit, VectorStore


def _normalise(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0  # a zero vector stays zero and scores 0 against everything
    return m / norms


class NumpyVectorStore(VectorStore):
    def __init__(self, path: Path):
        self._path = path
        self._ids: list[str] = []
        self._matrix: np.ndarray = np.empty((0, 0), dtype=np.float32)
        self._row: dict[str, int] = {}
        if path.exists():
            with np.load(path, allow_pickle=False) as data:
                self._ids = [str(i) for i in data["ids"]]
                self._matrix = data["vectors"].astype(np.float32)
            self._row = {i: n for n, i in enumerate(self._ids)}

    def upsert(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors must have the same length")
        if not ids:
            return
        if len(set(ids)) != len(ids):
            raise ValueError("ids must be unique within one upsert")
        new = _normalise(np.asarray(vectors, dtype=np.float32))
        if new.ndim != 2:
            raise ValueError("vectors must be a 2-D batch")
        if self._matrix.size and new.shape[1] != self._matrix.shape[1]:
            raise ValueError(f"dimension mismatch: store has {self._matrix.shape[1]}, got {new.shape[1]}")
        if not self._matrix.size:
            self._matrix = np.empty((0, new.shape[1]), dtype=np.float32)

        append_ids: list[str] = []
        append_rows: list[np.ndarray] = []
        for id_, vec in zip(ids, new, strict=True):
            if id_ in self._row:
                self._matrix[self._row[id_]] = vec
            else:
                append_ids.append(id_)
                append_rows.append(vec)
        if append_ids:
            start = len(self._ids)
            self._matrix = np.vstack([self._matrix, np.asarray(append_rows, dtype=np.float32)])
            self._ids.extend(append_ids)
            for offset, id_ in enumerate(append_ids):
                self._row[id_] = start + offset

    def query(self, vector: Sequence[float], k: int = 10) -> list[VectorHit]:
        if not self._ids or k <= 0:
            return []
        q = _normalise(np.asarray(vector, dtype=np.float32).reshape(1, -1))[0]
        if q.shape[0] != self._matrix.shape[1]:
            raise ValueError(f"dimension mismatch: store has {self._matrix.shape[1]}, got {q.shape[0]}")
        scores = self._matrix @ q
        k = min(k, len(self._ids))
        # Everything at or above the k-th best score, so exact ties are never split arbitrarily by
        # argpartition; then order by (score desc, id) and cut to k.
        threshold = np.partition(scores, -k)[-k]
        candidates = np.flatnonzero(scores >= threshold)
        order = sorted(candidates.tolist(), key=lambda i: (-float(scores[i]), self._ids[i]))[:k]
        return [VectorHit(id=self._ids[i], score=float(scores[i])) for i in order]

    def delete(self, ids: Sequence[str]) -> None:
        doomed = {self._row[i] for i in ids if i in self._row}
        if not doomed:
            return
        keep = [n for n in range(len(self._ids)) if n not in doomed]
        self._matrix = self._matrix[keep]
        self._ids = [self._ids[n] for n in keep]
        self._row = {i: n for n, i in enumerate(self._ids)}

    def count(self) -> int:
        return len(self._ids)

    def ids(self) -> list[str]:
        return list(self._ids)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        with open(tmp, "wb") as f:
            np.savez(f, ids=np.asarray(self._ids, dtype=str), vectors=self._matrix)
        os.replace(tmp, self._path)
