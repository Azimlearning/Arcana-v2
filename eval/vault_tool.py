"""Compile a vault beside a graph (M2.1, D-35). Free: no model call, no network.

    uv run python eval/vault_tool.py build --from data/g1/slice-atomic --to data/m2/slice-atomic-v1

Copies the source data directory (documents, vectors, graph and the ingestion report, never touching the source) into a NEW
directory and writes `vault.json` and `vault_build.json` there. The source graph, chunks and vectors are byte-identical in the
copy (their hashes are recorded and checked), so a later comparison changes only what the vault adds.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from api.vault.compile import compile_vault
from api.vault.local import JsonVaultStore
from eval.graph_variant import STORE_FILES, copy_database
from eval.run_ablation import chunks_sha256, git_state, sha256_file

VAULT_FILE = "vault.json"
BUILD_FILE = "vault_build.json"
COPIED = (*STORE_FILES, "variant.json")


def build(source: Path, target: Path) -> dict[str, Any]:
    for name in ("arcana.db", "graph.json", "vectors.npz"):
        if not (source / name).exists():
            raise SystemExit(f"{source} has no {name}")
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"{target} is not empty: a vault is built into a new directory")
    target.mkdir(parents=True, exist_ok=True)
    copy_database(source / "arcana.db", target / "arcana.db")
    for name in COPIED:
        if name != "arcana.db" and (source / name).exists():
            shutil.copyfile(source / name, target / name)

    docs = SqliteDocStore(make_engine(target / "arcana.db"))
    graph = NetworkXGraphStore(target / "graph.json")
    vault = compile_vault(graph, docs)
    store = JsonVaultStore(target / VAULT_FILE)
    store.put_vault(vault)
    store.save()
    chunks = docs.all_chunks()
    record = {
        "source": str(source),
        "code": git_state(),
        "vault_sha256": vault.sha256(),
        "stats": vault.stats,
        "hashes": {
            "graph_sha256": sha256_file(target / "graph.json"),
            "source_graph_sha256": sha256_file(source / "graph.json"),
            "vectors_sha256": sha256_file(target / "vectors.npz"),
            "source_vectors_sha256": sha256_file(source / "vectors.npz"),
            "chunks_sha256": chunks_sha256(chunks),
        },
    }
    h = record["hashes"]
    if (
        h["graph_sha256"] != h["source_graph_sha256"]
        or h["vectors_sha256"] != h["source_vectors_sha256"]
    ):
        raise SystemExit("the copy differs from its source: refusing to continue")
    (target / BUILD_FILE).write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="compile a vault into a new copy of a data directory")
    b.add_argument("--from", dest="source", required=True)
    b.add_argument("--to", dest="target", required=True)
    args = parser.parse_args(argv)
    record = build(Path(args.source), Path(args.target))
    print(json.dumps({"vault_sha256": record["vault_sha256"], **record["stats"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
