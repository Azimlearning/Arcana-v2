"""Dense and sparse retrievers, arm definitions, signal validation, and the protocol stamp."""

import pytest

from api.ingestion.embed import FakeEmbedder
from api.retrieval.arms import ARMS
from api.retrieval.dense import DenseRetriever
from api.retrieval.hybrid import hybrid_retrieve
from api.retrieval.protocol import protocol_stamp
from api.retrieval.sparse import SparseRetriever, tokenize
from api.retrieval.types import RetrievedChunk, RetrieverResult
from api.stores.doc_store import Chunk, Document
from api.stores.local.numpy_vector import NumpyVectorStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine


def test_the_five_arms_are_exactly_these_signal_sets():
    # Pinned as literals so a typo in ARMS cannot pass by being tested against itself.
    assert ARMS == {
        "dense": {"dense"},
        "sparse": {"sparse"},
        "graph": {"graph"},
        "flat": {"dense", "sparse"},
        "hybrid": {"dense", "sparse", "graph"},
    }


class Stub:
    def __init__(self, chunks: list[RetrievedChunk]):
        self.chunks = chunks

    async def retrieve(self, query: str, top_k: int = 10) -> RetrieverResult:
        return RetrieverResult(self.chunks)  # deliberately ignores top_k


def rc(i: int) -> RetrievedChunk:
    return RetrievedChunk(f"c{i:02d}", "d", "t", 1, 1.0, ("dense",))


async def test_unknown_signal_names_are_rejected_not_silently_dropped():
    s = Stub([])
    with pytest.raises(ValueError, match="sparsee"):
        await hybrid_retrieve("q", dense=s, sparse=s, graph=s, signals={"dense", "sparsee"})  # pyright: ignore[reportArgumentType]


async def test_a_retriever_returning_more_than_top_k_is_cut_to_top_k():
    many = Stub([rc(i) for i in range(25)])
    result = await hybrid_retrieve("q", dense=many, sparse=Stub([]), graph=Stub([]), signals={"dense"}, top_k=10)
    assert len(result.per_signal["dense"]) == 10 and len(result.chunks) == 10


def test_protocol_stamp_records_every_frozen_setting():
    stamp = protocol_stamp()
    assert stamp["rrf_k"] == 60 and stamp["top_k"] == 10
    assert stamp["chunking"] == {"target_chars": 1200, "overlap_chars": 200}
    assert stamp["graph"]["scoring_version"] == "p0-2" and stamp["graph"]["hops"] == 1
    assert stamp["entity_resolution"]["max_approx"] == 3
    assert stamp == protocol_stamp()  # deterministic: same code, same stamp


# ── SparseRetriever / DenseRetriever on a tiny handmade corpus ────────────────


def corpus(tmp_path, texts: dict[str, str]):
    docs = SqliteDocStore(make_engine(tmp_path / "a.db"))
    docs.put_document(Document("d", "T", "t.pdf", "ready", 1, None, "2026-10-05"))
    docs.put_chunks([Chunk(cid, "d", i, 1, text) for i, (cid, text) in enumerate(texts.items())])
    return docs


def test_tokenizer_is_ascii_lowercase_and_stable():
    # ASCII only on purpose (reproducible across machines): a non-ASCII letter acts as a separator.
    assert tokenize("BM25 beats Dense-Retrieval, café!") == ["bm25", "beats", "dense", "retrieval", "caf"]


async def test_sparse_ranks_the_term_holder_first_and_drops_non_positive_scores(tmp_path):
    docs = corpus(tmp_path, {"a": "louvain communities in graphs", "b": "plain text here", "c": "more plain text"})
    out = await SparseRetriever(docs=docs).retrieve("louvain")
    assert [c.id for c in out.chunks] == ["a"] and out.chunks[0].sources == ("sparse",)
    assert out.chunks[0].score > 0 and out.resolution is None


async def test_sparse_with_a_query_of_no_tokens_or_an_empty_corpus_is_empty(tmp_path):
    docs = corpus(tmp_path, {"a": "text"})
    assert (await SparseRetriever(docs=docs).retrieve("???")).chunks == []
    empty = SqliteDocStore(make_engine(tmp_path / "e.db"))
    assert (await SparseRetriever(docs=empty).retrieve("anything")).chunks == []


async def test_dense_returns_nearest_first_with_dense_as_source(tmp_path):
    texts = {"a": "dense retrieval of passages", "b": "zebra giraffe lion", "c": "dense passages"}
    docs = corpus(tmp_path, texts)
    vectors = NumpyVectorStore(tmp_path / "v.npz")
    embedder = FakeEmbedder()
    vectors.upsert(list(texts), await embedder.embed(list(texts.values())))
    out = await DenseRetriever(vectors=vectors, docs=docs, embedder=embedder).retrieve("dense retrieval", top_k=2)
    assert [c.id for c in out.chunks] == ["a", "c"] and all(c.sources == ("dense",) for c in out.chunks)
    assert out.chunks[0].score >= out.chunks[1].score


async def test_dense_skips_a_vector_whose_chunk_no_longer_exists(tmp_path):
    docs = corpus(tmp_path, {"a": "dense retrieval"})
    vectors = NumpyVectorStore(tmp_path / "v.npz")
    embedder = FakeEmbedder()
    vectors.upsert(["a", "ghost"], await embedder.embed(["dense retrieval", "dense retrieval"]))
    out = await DenseRetriever(vectors=vectors, docs=docs, embedder=embedder).retrieve("dense retrieval")
    assert [c.id for c in out.chunks] == ["a"]


async def test_dense_on_an_empty_store_or_blank_query_is_empty(tmp_path):
    docs = corpus(tmp_path, {"a": "x"})
    retriever = DenseRetriever(vectors=NumpyVectorStore(tmp_path / "v.npz"), docs=docs, embedder=FakeEmbedder())
    assert (await retriever.retrieve("anything")).chunks == []
    assert (await retriever.retrieve("   ")).chunks == []
