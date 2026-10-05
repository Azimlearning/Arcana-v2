"""SQLite DocStore via SQLAlchemy (D-09). One file holds documents, chunks and turns; the spend
ledger (api/llm/ledger.py) shares the same file through the same engine."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import (
    Column,
    Engine,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    event,
    select,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from api.stores.doc_store import Chunk, DocStatus, DocStore, Document, Turn

metadata = MetaData()

documents = Table(
    "documents",
    metadata,
    Column("id", String, primary_key=True),
    Column("title", String, nullable=False),
    Column("source_path", String, nullable=False),
    Column("status", String, nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("error", Text),
    Column("created_at", String, nullable=False),
)

chunks = Table(
    "chunks",
    metadata,
    Column("id", String, primary_key=True),
    Column("doc_id", String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("ordinal", Integer, nullable=False),
    Column("page", Integer),
    Column("text", Text, nullable=False),
)

turns = Table(
    "turns",
    metadata,
    Column("id", String, primary_key=True),
    Column("created_at", String, nullable=False),
    Column("query", Text, nullable=False),
    Column("outcome", String, nullable=False),
    Column("latency_ms", Integer, nullable=False),
    Column("error_code", String),
)


def make_engine(path: Path) -> Engine:
    """The one SQLite engine for the data directory. Foreign keys on, WAL for concurrent readers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):  # pyright: ignore[reportUnusedFunction]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return engine


def _doc(row) -> Document:
    return Document(
        id=row.id,
        title=row.title,
        source_path=row.source_path,
        status=row.status,
        size_bytes=row.size_bytes,
        error=row.error,
        created_at=row.created_at,
    )


def _chunk(row) -> Chunk:
    return Chunk(id=row.id, doc_id=row.doc_id, ordinal=row.ordinal, page=row.page, text=row.text)


def _upsert(table: Table, values: dict):
    stmt = sqlite_insert(table).values(**values)
    return stmt.on_conflict_do_update(
        index_elements=[table.c.id], set_={k: v for k, v in values.items() if k != "id"}
    )


class SqliteDocStore(DocStore):
    def __init__(self, engine: Engine):
        self.engine = engine
        metadata.create_all(engine)

    def put_document(self, doc: Document) -> None:
        values = {
            "id": doc.id,
            "title": doc.title,
            "source_path": doc.source_path,
            "status": doc.status,
            "size_bytes": doc.size_bytes,
            "error": doc.error,
            "created_at": doc.created_at,
        }
        with self.engine.begin() as conn:
            conn.execute(_upsert(documents, values))

    def set_status(self, doc_id: str, status: DocStatus, error: str | None = None) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                documents.update().where(documents.c.id == doc_id).values(status=status, error=error)
            )

    def get_document(self, doc_id: str) -> Document | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(documents).where(documents.c.id == doc_id)).first()
        return _doc(row) if row else None

    def list_documents(self) -> list[Document]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(documents).order_by(documents.c.created_at, documents.c.id))
            return [_doc(r) for r in rows]

    def put_chunks(self, items: Sequence[Chunk]) -> None:
        with self.engine.begin() as conn:
            for c in items:
                conn.execute(
                    _upsert(
                        chunks,
                        {"id": c.id, "doc_id": c.doc_id, "ordinal": c.ordinal, "page": c.page, "text": c.text},
                    )
                )

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        return self.get_chunks([chunk_id]).get(chunk_id)

    def get_chunks(self, chunk_ids: Sequence[str]) -> dict[str, Chunk]:
        if not chunk_ids:
            return {}
        with self.engine.connect() as conn:
            rows = conn.execute(select(chunks).where(chunks.c.id.in_(list(chunk_ids))))
            return {r.id: _chunk(r) for r in rows}

    def chunks_for_document(self, doc_id: str) -> list[Chunk]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(chunks).where(chunks.c.doc_id == doc_id).order_by(chunks.c.ordinal)
            )
            return [_chunk(r) for r in rows]

    def all_chunks(self) -> list[Chunk]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(chunks).order_by(chunks.c.doc_id, chunks.c.ordinal))
            return [_chunk(r) for r in rows]

    def delete_document(self, doc_id: str) -> list[str]:
        with self.engine.begin() as conn:
            ids = [r.id for r in conn.execute(select(chunks.c.id).where(chunks.c.doc_id == doc_id))]
            conn.execute(delete(chunks).where(chunks.c.doc_id == doc_id))
            conn.execute(delete(documents).where(documents.c.id == doc_id))
        return ids

    def record_turn(self, turn: Turn) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                _upsert(
                    turns,
                    {
                        "id": turn.id,
                        "created_at": turn.created_at,
                        "query": turn.query,
                        "outcome": turn.outcome,
                        "latency_ms": turn.latency_ms,
                        "error_code": turn.error_code,
                    },
                )
            )

    def turns(self) -> list[Turn]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(turns).order_by(turns.c.created_at, turns.c.id))
            return [
                Turn(
                    id=r.id,
                    created_at=r.created_at,
                    query=r.query,
                    outcome=r.outcome,
                    latency_ms=r.latency_ms,
                    error_code=r.error_code,
                )
                for r in rows
            ]
