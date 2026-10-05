"""End to end on the fixture PDF, with real local stores and fake providers."""

from api.ingestion.fakes import fake_extraction_responder
from api.ingestion.pipeline import ingest_pdf
from api.llm.providers.fake import FakeProvider

# The fixture is 3 pages, 3,544 characters: at 1,200 / 200 that is 4 chunks. If the fixture or the
# chunker settings change, this number must change on purpose.
EXPECTED_CHUNKS = 4


async def test_fixture_pdf_ingests_end_to_end(pdf_bytes, make_deps):
    deps = make_deps()
    result = await ingest_pdf(pdf_bytes, "hybrid_retrieval.pdf", deps)

    assert result.status == "ready" and result.error is None
    assert result.title == "Hybrid Retrieval over Knowledge Graphs"
    assert result.chunk_count == EXPECTED_CHUNKS == len(deps.docs.chunks_for_document(result.doc_id))

    # every chunk has a vector, and a chunk's own embedding finds that chunk first
    chunks = deps.docs.chunks_for_document(result.doc_id)
    assert deps.vectors.count() == len(chunks)
    (vec,) = await deps.embedder.embed([chunks[2].text])
    assert deps.vectors.query(vec, k=1)[0].id == chunks[2].id

    # the graph has nodes, shared across chunks, and every edge's chunk id resolves to a stored chunk
    assert result.node_count > 0 and result.edge_count > 0 and result.extraction_failures == 0
    nodes, edges = deps.graph.nodes(), deps.graph.edges()
    assert nodes and edges
    stored = deps.docs.get_chunks([e.chunk_id for e in edges])
    assert all(e.chunk_id in stored for e in edges)
    assert all(e.doc_id == result.doc_id for e in edges)
    assert any(n.id == "dense_retrieval" for n in nodes)  # a term the fixture repeats across pages

    document = deps.docs.get_document(result.doc_id)
    assert document is not None and document.status == "ready"


async def test_results_persist_to_disk(pdf_bytes, make_deps, tmp_path):
    deps = make_deps()
    result = await ingest_pdf(pdf_bytes, "f.pdf", deps)
    from api.stores.local.networkx_graph import NetworkXGraphStore
    from api.stores.local.numpy_vector import NumpyVectorStore

    assert NumpyVectorStore(tmp_path / "vectors.npz").count() == result.chunk_count
    assert len(NetworkXGraphStore(tmp_path / "graph.json").edges()) == len(deps.graph.edges())


async def test_reingesting_the_same_file_replaces_it(pdf_bytes, make_deps):
    deps = make_deps()
    first = await ingest_pdf(pdf_bytes, "f.pdf", deps)
    edges_before = len(deps.graph.edges())
    second = await ingest_pdf(pdf_bytes, "f.pdf", deps)
    assert first.doc_id == second.doc_id
    assert deps.vectors.count() == EXPECTED_CHUNKS
    assert len(deps.docs.all_chunks()) == EXPECTED_CHUNKS
    assert len(deps.graph.edges()) == edges_before
    assert len(deps.docs.list_documents()) == 1


async def test_a_malformed_extraction_reply_costs_the_chunk_its_graph_only(pdf_bytes, make_deps):
    def sometimes_broken(request):
        return "not json" if "Ablation" in request.prompt else fake_extraction_responder(request)

    deps = make_deps(provider=FakeProvider(sometimes_broken))
    result = await ingest_pdf(pdf_bytes, "f.pdf", deps)
    assert result.status == "ready" and result.extraction_failures >= 1
    assert deps.vectors.count() == EXPECTED_CHUNKS  # text and vectors are untouched
    assert result.edge_count > 0


async def test_a_provider_outage_fails_the_document_and_leaves_nothing_behind(pdf_bytes, make_deps):
    deps = make_deps(provider=FakeProvider(fail_with="timeout"))
    result = await ingest_pdf(pdf_bytes, "f.pdf", deps)
    assert result.status == "failed"
    assert "provider" in (result.error or "").lower()
    assert deps.vectors.count() == 0 and deps.graph.nodes() == [] and deps.docs.all_chunks() == []
    document = deps.docs.get_document(result.doc_id)
    assert document is not None and document.status == "failed" and document.error


async def test_a_spend_cap_hit_during_extraction_fails_the_document_cleanly(pdf_bytes, make_deps):
    # Priced like Anthropic so the cap bites; far too small for four extraction calls.
    deps = make_deps(provider=FakeProvider(fake_extraction_responder, name="anthropic"), cap=1e-9)
    result = await ingest_pdf(pdf_bytes, "f.pdf", deps)
    assert result.status == "failed" and "cap" in (result.error or "").lower()
    assert deps.vectors.count() == 0 and deps.docs.all_chunks() == []


async def test_a_file_that_is_not_a_pdf_is_reported_not_raised(make_deps):
    result = await ingest_pdf(b"this is plainly not a pdf", "notes.pdf", make_deps())
    assert result.status == "failed" and result.chunk_count == 0 and result.error


async def test_an_empty_upload_is_reported(make_deps):
    result = await ingest_pdf(b"", "empty.pdf", make_deps())
    assert result.status == "failed" and result.error


async def test_a_pdf_without_text_is_reported_as_unextractable(make_deps):
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()  # one blank page, like a scan with no text layer
    blank = doc.tobytes()
    doc.close()
    result = await ingest_pdf(blank, "scan.pdf", make_deps())
    assert result.status == "failed" and "No extractable text" in (result.error or "")


async def test_every_node_chunk_id_resolves_to_a_stored_chunk(pdf_bytes, make_deps):
    deps = make_deps()
    result = await ingest_pdf(pdf_bytes, "f.pdf", deps)
    nodes = deps.graph.nodes()
    mentioned = {c for n in nodes for c in n.chunk_ids}
    stored = deps.docs.get_chunks(sorted(mentioned))
    assert mentioned and mentioned == set(stored)
    assert all(n.chunk_ids for n in nodes)  # no node is untraceable
    # a re-ingest leaves no stale chunk ids behind
    await ingest_pdf(pdf_bytes, "f.pdf", deps)
    after = {c for n in deps.graph.nodes() for c in n.chunk_ids}
    assert after == mentioned and result.chunk_count == EXPECTED_CHUNKS


async def test_cancelling_an_ingest_leaves_nothing_visible_to_any_signal(pdf_bytes, make_deps):
    import asyncio

    from api.ingestion.embed import FakeEmbedder
    from api.stores.preflight import check_corpus_parity

    class Slow(FakeEmbedder):
        async def embed(self, texts):
            await asyncio.sleep(10)  # cancelled while embedding, after chunks were already stored
            return await super().embed(texts)

    deps = make_deps(embedder=Slow())
    task = asyncio.ensure_future(ingest_pdf(pdf_bytes, "f.pdf", deps))
    await asyncio.sleep(0.2)
    assert deps.docs.all_chunks()  # chunks really were stored before the embed step
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert deps.docs.all_chunks() == [] and deps.vectors.count() == 0 and deps.graph.nodes() == []
    # The only note allowed is the failed document row itself: no chunk/vector/graph asymmetry.
    problems = check_corpus_parity(deps.docs, deps.vectors, deps.graph)
    assert problems and all("not ready" in p for p in problems)
