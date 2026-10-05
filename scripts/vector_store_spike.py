"""Q-02 spike: which local vector store handles 3,072-dim vectors on this machine without a server?

Usage (one candidate per isolated environment, so the project environment is never touched):

    uv run --no-project --python 3.13 --with numpy --with chromadb python scripts/vector_store_spike.py chromadb

Each candidate: insert 2,000 random 3,072-dim vectors, run 20 cosine top-10 queries, check recall@10
against exact numpy brute force, then close, reopen from disk and re-query (persistence). Prints one
JSON line. Exit code 0 even when a candidate fails: failure is a result, recorded as an error field.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np

DIM = 3072
N = 2000
Q = 20
K = 10
SEED = 7


def normalise(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=-1, keepdims=True)


def make_data() -> tuple[np.ndarray, np.ndarray, list[list[int]]]:
    rng = np.random.default_rng(SEED)
    vectors = rng.standard_normal((N, DIM), dtype=np.float32)
    queries = rng.standard_normal((Q, DIM), dtype=np.float32)
    exact = np.argsort(-(normalise(queries) @ normalise(vectors).T), axis=1)[:, :K]
    return vectors, queries, [list(map(int, row)) for row in exact]


def recall(found: list[list[int]], exact: list[list[int]]) -> float:
    hits = sum(len(set(f) & set(e)) for f, e in zip(found, exact, strict=True))
    return hits / (len(exact) * K)


# Each candidate returns (build, open_and_query): build(dir, vectors) writes to disk and closes;
# open_and_query(dir, queries) reopens from disk and returns top-K id lists per query.


def numpy_store():
    def build(d: Path, v: np.ndarray):
        np.save(d / "v.npy", normalise(v).astype(np.float32))

    def query(d: Path, q: np.ndarray):
        m = np.load(d / "v.npy")
        scores = normalise(q) @ m.T
        return [list(map(int, r)) for r in np.argsort(-scores, axis=1)[:, :K]]

    return build, query


def chromadb_store():
    import chromadb

    def build(d: Path, v: np.ndarray):
        client = chromadb.PersistentClient(path=str(d))
        col = client.create_collection("chunks", metadata={"hnsw:space": "cosine"})
        for start in range(0, len(v), 500):
            chunk = v[start : start + 500]
            col.add(ids=[str(i) for i in range(start, start + len(chunk))], embeddings=chunk.tolist())

    def query(d: Path, q: np.ndarray):
        col = chromadb.PersistentClient(path=str(d)).get_collection("chunks")
        res = col.query(query_embeddings=q.tolist(), n_results=K)
        return [[int(i) for i in ids] for ids in res["ids"]]

    return build, query


def lancedb_store():
    import lancedb
    import pyarrow as pa

    def build(d: Path, v: np.ndarray):
        db = lancedb.connect(str(d))
        table = pa.table(
            {
                "id": pa.array(range(len(v)), pa.int64()),
                "vector": pa.FixedSizeListArray.from_arrays(pa.array(v.reshape(-1)), DIM),
            }
        )
        db.create_table("t", data=table)

    def query(d: Path, q: np.ndarray):
        tbl = lancedb.connect(str(d)).open_table("t")
        return [
            [int(r["id"]) for r in tbl.search(row).metric("cosine").limit(K).to_list()]
            for row in q
        ]

    return build, query


def faiss_store():
    import faiss

    def build(d: Path, v: np.ndarray):
        index = faiss.IndexFlatIP(DIM)
        index.add(normalise(v).astype(np.float32))
        faiss.write_index(index, str(d / "i.faiss"))

    def query(d: Path, q: np.ndarray):
        index = faiss.read_index(str(d / "i.faiss"))
        _, ids = index.search(normalise(q).astype(np.float32), K)
        return [list(map(int, r)) for r in ids]

    return build, query


def sqlite_vec_store():
    import sqlite3

    import sqlite_vec

    def connect(d: Path):
        conn = sqlite3.connect(str(d / "v.db"))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn

    def build(d: Path, v: np.ndarray):
        conn = connect(d)
        conn.execute(f"create virtual table vec using vec0(embedding float[{DIM}] distance_metric=cosine)")
        with conn:
            conn.executemany(
                "insert into vec(rowid, embedding) values (?, ?)",
                [(i, sqlite_vec.serialize_float32(row.tolist())) for i, row in enumerate(v)],
            )
        conn.close()

    def query(d: Path, q: np.ndarray):
        conn = connect(d)
        out = []
        for row in q:
            rows = conn.execute(
                "select rowid from vec where embedding match ? and k = ?",
                (sqlite_vec.serialize_float32(row.tolist()), K),
            ).fetchall()
            out.append([int(r[0]) for r in rows])
        conn.close()
        return out

    return build, query


def usearch_store():
    from usearch.index import Index

    def build(d: Path, v: np.ndarray):
        index = Index(ndim=DIM, metric="cos")
        index.add(np.arange(len(v)), v)
        index.save(str(d / "i.usearch"))

    def query(d: Path, q: np.ndarray):
        index = Index.restore(str(d / "i.usearch"))
        found = index.search(q, K)
        return [list(map(int, row[: len(row)])) for row in found.keys]

    return build, query


def hnswlib_store():
    import hnswlib

    def build(d: Path, v: np.ndarray):
        index = hnswlib.Index(space="cosine", dim=DIM)
        index.init_index(max_elements=len(v), ef_construction=200, M=16)
        index.add_items(v, np.arange(len(v)))
        index.save_index(str(d / "i.hnsw"))

    def query(d: Path, q: np.ndarray):
        index = hnswlib.Index(space="cosine", dim=DIM)
        index.load_index(str(d / "i.hnsw"), max_elements=N)
        index.set_ef(100)
        labels, _ = index.knn_query(q, k=K)
        return [list(map(int, r)) for r in labels]

    return build, query


CANDIDATES = {
    "numpy": numpy_store,
    "chromadb": chromadb_store,
    "lancedb": lancedb_store,
    "faiss-cpu": faiss_store,
    "sqlite-vec": sqlite_vec_store,
    "usearch": usearch_store,
    "hnswlib": hnswlib_store,
}


def run(name: str) -> dict:
    result: dict = {"candidate": name, "python": sys.version.split()[0]}
    vectors, queries, exact = make_data()
    workdir = Path(tempfile.mkdtemp(prefix=f"spike-{name}-"))
    try:
        t0 = time.perf_counter()
        build, query = CANDIDATES[name]()
        result["import_s"] = round(time.perf_counter() - t0, 3)

        t0 = time.perf_counter()
        build(workdir, vectors)
        result["insert_2000_s"] = round(time.perf_counter() - t0, 3)
        result["on_disk_mb"] = round(
            sum(f.stat().st_size for f in workdir.rglob("*") if f.is_file()) / 1e6, 1
        )

        # Reopen from disk (persistence) and time the 20 queries.
        t0 = time.perf_counter()
        found = query(workdir, queries)
        elapsed = time.perf_counter() - t0
        result["query_20_s_incl_reopen"] = round(elapsed, 3)
        result["recall_at_10"] = round(recall(found, exact), 3)
        result["persisted"] = len(found) == Q and all(len(r) == K for r in found)

        # Steady-state query time: a second pass on a warm process.
        t0 = time.perf_counter()
        query(workdir, queries)
        result["query_20_s_second_pass"] = round(time.perf_counter() - t0, 3)
        result["ok"] = result["persisted"] and result["recall_at_10"] >= 0.9
    except Exception as exc:  # a failing candidate is a result, not a crash
        result["ok"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["trace_tail"] = traceback.format_exc().strip().splitlines()[-3:]
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return result


if __name__ == "__main__":
    candidate = sys.argv[1]
    print(json.dumps(run(candidate)))
