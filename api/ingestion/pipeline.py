"""PDF to chunks, vectors and graph in one pass (benchmark protocol: one extraction pass per chunk).

Order: parse, chunk, store chunks, embed and store vectors, extract and store graph, then persist.
Every graph edge records the chunk it came from. Re-ingesting the same file replaces it: the
document id is a hash of the bytes, and anything stored under that id is removed first.

If a step fails after storage began, everything stored for the document is removed and the document
row is left as `failed` with a reason, so a half-ingested document never answers queries.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from api.core.errors import ArcanaError, IngestFailed
from api.core.logging import get_logger
from api.ingestion.chunk import chunk
from api.ingestion.embed import Embedder
from api.ingestion.extract import ExtractionResult, extract_chunk
from api.ingestion.parse import parse
from api.ingestion.types import IngestResult, doc_id_for
from api.llm.service import LLMService
from api.stores.doc_store import Chunk, DocStore, Document
from api.stores.graph_store import GraphStore
from api.stores.vector_store import VectorStore

log = get_logger(__name__)

EXTRACTION_CONCURRENCY = 4


@dataclass
class IngestDeps:
    docs: DocStore
    vectors: VectorStore
    graph: GraphStore
    embedder: Embedder
    llm: LLMService


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _remove(doc_id: str, deps: IngestDeps) -> None:
    """Delete everything stored for a document, across all three stores."""
    chunk_ids = [c.id for c in deps.docs.chunks_for_document(doc_id)]
    deps.vectors.delete(chunk_ids)
    deps.graph.delete_document(doc_id, chunk_ids)
    deps.docs.delete_document(doc_id)


async def ingest_pdf(raw: bytes, filename: str, deps: IngestDeps) -> IngestResult:
    doc_id = doc_id_for(raw)
    fallback_title = filename.rsplit(".", 1)[0] or filename

    if deps.docs.get_document(doc_id) is not None:
        _remove(doc_id, deps)  # same bytes ingested before: replace, never duplicate

    def failed(message: str, title: str = fallback_title) -> IngestResult:
        deps.docs.put_document(
            Document(doc_id, title, filename, "failed", len(raw), message, _now())
        )
        return IngestResult(doc_id, title, "failed", 0, 0, 0, 0, message)

    try:
        parsed = parse(raw)
    except IngestFailed as exc:
        return failed(exc.message)

    title = parsed.title or fallback_title
    chunks = chunk(parsed.pages, doc_id=doc_id)
    if not chunks:
        return failed("No extractable text: the PDF may be scanned images (OCR is not supported).", title)

    deps.docs.put_document(Document(doc_id, title, filename, "parsing", len(raw), None, _now()))
    try:
        deps.docs.put_chunks(chunks)

        deps.docs.set_status(doc_id, "embedding")
        vectors = await deps.embedder.embed([c.text for c in chunks])
        deps.vectors.upsert([c.id for c in chunks], vectors)

        results = await _extract_all(chunks, deps.llm)
        node_total, edge_total, extraction_failures = _write_graph(results, deps.graph)

        deps.graph.save()
        deps.vectors.save()
        deps.docs.set_status(doc_id, "ready")
    except BaseException as exc:  # includes cancellation: a half-ingested document must never answer queries
        message = exc.message if isinstance(exc, ArcanaError) else "Ingestion failed unexpectedly."
        log.error("ingest_failed", doc_id=doc_id, error=type(exc).__name__)
        _remove(doc_id, deps)
        deps.graph.save()
        deps.vectors.save()
        result = failed(message, title)
        if isinstance(exc, ArcanaError):
            return result  # an expected failure (spend cap, provider down): reported, not raised
        raise  # a bug: the document is cleaned up and marked failed, but it must not be swallowed

    log.info(
        "ingested",
        doc_id=doc_id,
        chunks=len(chunks),
        nodes=node_total,
        edges=edge_total,
        extraction_failures=extraction_failures,
    )
    return IngestResult(
        doc_id, title, "ready", len(chunks), node_total, edge_total, extraction_failures, None
    )


async def _extract_all(chunks: list[Chunk], llm: LLMService) -> list[ExtractionResult | None]:
    """One extraction per chunk, a few at a time. A malformed reply gives None for that chunk; any
    other failure (provider down, spend cap) cancels the rest and propagates."""
    gate = asyncio.Semaphore(EXTRACTION_CONCURRENCY)

    async def one(c: Chunk) -> ExtractionResult | None:
        async with gate:
            try:
                return await extract_chunk(c, llm)
            except IngestFailed:
                log.warning("extraction_malformed", chunk_id=c.id)
                return None

    tasks = [asyncio.ensure_future(one(c)) for c in chunks]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for t in tasks:
            t.cancel()
        raise


def _write_graph(
    results: list[ExtractionResult | None], graph: GraphStore
) -> tuple[int, int, int]:
    """Merge every chunk's nodes then edges into the graph. Returns (nodes, edges, malformed)."""
    node_ids: set[str] = set()
    edge_count = 0
    malformed = 0
    for result in results:
        if result is None:
            malformed += 1
            continue
        for node in result.nodes:
            graph.upsert_node(node)
            node_ids.add(node.id)
        for edge in result.edges:
            graph.upsert_edge(edge)
            edge_count += 1
    return len(node_ids), edge_count, malformed
