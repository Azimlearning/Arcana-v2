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

from api.stores.doc_store import Chunk, DocStatus, DocStore, Document, StoredPattern, Turn

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

# A separate table, not a column on `turns`: create_all adds a missing table but never alters an existing
# one, so a data directory created before traces existed still opens. No foreign key to `turns`: the trace
# and the turn row are written independently.
turn_traces = Table(
    "turn_traces",
    metadata,
    Column("turn_id", String, primary_key=True),
    Column("trace_json", Text, nullable=False),
)


# New tables, like `turn_traces`: create_all adds a missing table and never alters an existing one, so a data
# directory created before they existed still opens and gains them.
turn_views = Table(
    "turn_views",
    metadata,
    Column("turn_id", String, primary_key=True),
    Column("view_json", Text, nullable=False),
)

ui_patterns = Table(
    "ui_patterns",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("template_id", String, nullable=False),
    Column("template_version", Integer, nullable=False),
    Column("params_json", Text, nullable=False),
    Column("layout_mode", String, nullable=False),
    Column("state", String, nullable=False),
    Column("use_count", Integer, nullable=False),
    Column("created_at", String, nullable=False),
    Column("last_used_at", String),
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


def _pattern(row) -> StoredPattern:
    return StoredPattern(
        id=row.id,
        name=row.name,
        template_id=row.template_id,
        template_version=row.template_version,
        params_json=row.params_json,
        layout_mode=row.layout_mode,
        state=row.state,
        use_count=row.use_count,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )


def _upsert(table: Table, values: dict, key: str = "id"):
    stmt = sqlite_insert(table).values(**values)
    return stmt.on_conflict_do_update(
        index_elements=[table.c[key]], set_={k: v for k, v in values.items() if k != key}
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

    def record_trace(self, turn_id: str, trace_json: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(_upsert(turn_traces, {"turn_id": turn_id, "trace_json": trace_json}, key="turn_id"))

    def get_trace(self, turn_id: str) -> str | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(turn_traces.c.trace_json).where(turn_traces.c.turn_id == turn_id)).first()
            return row[0] if row else None

    def record_view(self, turn_id: str, view_json: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(_upsert(turn_views, {"turn_id": turn_id, "view_json": view_json}, key="turn_id"))

    def get_view(self, turn_id: str) -> str | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(turn_views.c.view_json).where(turn_views.c.turn_id == turn_id)).first()
            return row[0] if row else None

    def put_pattern(self, pattern: StoredPattern) -> StoredPattern:
        values = {
            "id": pattern.id,
            "name": pattern.name,
            "template_id": pattern.template_id,
            "template_version": pattern.template_version,
            "params_json": pattern.params_json,
            "layout_mode": pattern.layout_mode,
            "state": pattern.state,
            "use_count": pattern.use_count,
            "created_at": pattern.created_at,
            "last_used_at": pattern.last_used_at,
        }
        with self.engine.begin() as conn:
            conn.execute(sqlite_insert(ui_patterns).values(**values).on_conflict_do_nothing(index_elements=["id"]))
        stored = self.get_pattern(pattern.id)
        assert stored is not None
        return stored

    def get_pattern(self, pattern_id: str) -> StoredPattern | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(ui_patterns).where(ui_patterns.c.id == pattern_id)).first()
            return _pattern(row) if row else None

    def list_patterns(self) -> list[StoredPattern]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(ui_patterns).order_by(ui_patterns.c.created_at, ui_patterns.c.id)).all()
            return [_pattern(r) for r in rows]

    def delete_pattern(self, pattern_id: str) -> bool:
        with self.engine.begin() as conn:
            return conn.execute(delete(ui_patterns).where(ui_patterns.c.id == pattern_id)).rowcount > 0

    def mark_pattern_used(self, pattern_id: str, when: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                ui_patterns.update()
                .where(ui_patterns.c.id == pattern_id)
                .values(use_count=ui_patterns.c.use_count + 1, last_used_at=when)
            )

    def update_pattern(self, pattern_id: str, *, state: str, template_version: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                ui_patterns.update()
                .where(ui_patterns.c.id == pattern_id)
                .values(state=state, template_version=template_version)
            )
