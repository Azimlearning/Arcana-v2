"""Wires stores, providers and retrievers for the configured mode. Built once, at app startup."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine

from api.core.settings import Settings
from api.fakes import fake_llm_responder
from api.ingestion.embed import Embedder, build_embedder
from api.ingestion.pipeline import IngestDeps
from api.llm.factory import build_llm_service
from api.llm.ledger import SpendLedger
from api.llm.service import LLMService
from api.retrieval.dense import DenseRetriever
from api.retrieval.graph import GraphRetriever
from api.retrieval.hybrid import hybrid_retrieve
from api.retrieval.sparse import SparseRetriever
from api.retrieval.types import RetrievalResult
from api.stores.doc_store import DocStore
from api.stores.graph_store import GraphStore
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.numpy_vector import NumpyVectorStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from api.stores.vector_store import VectorStore


@dataclass
class Container:
    settings: Settings
    engine: Engine
    docs: DocStore
    vectors: VectorStore
    graph: GraphStore
    ledger: SpendLedger
    llm: LLMService
    embedder: Embedder
    uploads_dir: Path

    @property
    def ingest_deps(self) -> IngestDeps:
        return IngestDeps(
            docs=self.docs,
            vectors=self.vectors,
            graph=self.graph,
            embedder=self.embedder,
            llm=self.llm,
        )

    async def retrieve(self, query: str) -> RetrievalResult:
        """The evidence path: all three signals, fused (the `hybrid` arm)."""
        return await hybrid_retrieve(
            query,
            dense=DenseRetriever(vectors=self.vectors, docs=self.docs, embedder=self.embedder),
            sparse=SparseRetriever(docs=self.docs),
            graph=GraphRetriever(graph=self.graph, docs=self.docs),
        )


def build_container(settings: Settings) -> Container:
    data = settings.arcana_data_dir
    data.mkdir(parents=True, exist_ok=True)
    engine = make_engine(data / "arcana.db")
    ledger = SpendLedger(engine, settings.llm_monthly_cap_usd)
    return Container(
        settings=settings,
        engine=engine,
        docs=SqliteDocStore(engine),
        vectors=NumpyVectorStore(data / "vectors.npz"),
        graph=NetworkXGraphStore(data / "graph.json"),
        ledger=ledger,
        llm=build_llm_service(settings, ledger, fake_responder=fake_llm_responder),
        embedder=build_embedder(settings, ledger),
        uploads_dir=data / "uploads",
    )
