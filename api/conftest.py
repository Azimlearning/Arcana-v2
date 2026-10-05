"""Shared fixtures: the fixture PDF and a factory that wires real local stores to fake providers."""

from collections.abc import Callable
from pathlib import Path

import pytest

from api.ingestion.embed import Embedder, FakeEmbedder
from api.ingestion.fakes import fake_extraction_responder
from api.ingestion.pipeline import IngestDeps
from api.llm.ledger import SpendLedger
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.numpy_vector import NumpyVectorStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine

FIXTURE_PDF = Path(__file__).parent / "tests" / "fixtures" / "hybrid_retrieval.pdf"


@pytest.fixture
def pdf_bytes() -> bytes:
    return FIXTURE_PDF.read_bytes()


@pytest.fixture
def make_deps(tmp_path: Path) -> Callable[..., IngestDeps]:
    """Build IngestDeps over real local stores in tmp_path. Everything paid is fake by default."""

    def _make(
        *,
        provider: FakeProvider | None = None,
        embedder: Embedder | None = None,
        cap: float | None = None,
    ) -> IngestDeps:
        engine = make_engine(tmp_path / "arcana.db")
        docs = SqliteDocStore(engine)
        ledger = SpendLedger(engine, cap)
        llm = LLMService(provider or FakeProvider(fake_extraction_responder), None, ledger)
        return IngestDeps(
            docs=docs,
            vectors=NumpyVectorStore(tmp_path / "vectors.npz"),
            graph=NetworkXGraphStore(tmp_path / "graph.json"),
            embedder=embedder or FakeEmbedder(),
            llm=llm,
        )

    return _make


@pytest.fixture
async def ingested(pdf_bytes: bytes, make_deps: Callable[..., IngestDeps]):
    """The fixture PDF ingested into real local stores with fake providers: (deps, IngestResult)."""
    from api.ingestion.pipeline import ingest_pdf

    deps = make_deps()
    return deps, await ingest_pdf(pdf_bytes, "hybrid_retrieval.pdf", deps)
