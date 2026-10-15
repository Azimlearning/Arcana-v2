"""Wires stores, providers and retrievers for the configured mode. Built once, at app startup."""

import threading
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine

from api.core.settings import Settings
from api.fakes import fake_llm_responder
from api.genui.templates import ensure_builtin_registered
from api.ingestion.embed import Embedder, build_embedder
from api.ingestion.pipeline import IngestDeps
from api.labs.contract import CONTRACTS
from api.labs.generator import FakeLabGenerator, LabGenerator
from api.labs.live_generator import LiveLabGenerator
from api.labs.store import LabStore, SqliteLabStore
from api.labs.verifier import TEMPLATE_VERSION, contract_sha256
from api.learner.store import LearnerStore, SqliteLearnerStore
from api.llm.factory import build_llm_service
from api.llm.ledger import SpendLedger
from api.llm.service import LLMService
from api.retrieval.dense import DenseRetriever
from api.retrieval.graph import GraphRetriever
from api.retrieval.hybrid import hybrid_retrieve
from api.retrieval.sparse import SparseRetriever
from api.retrieval.types import CANDIDATE_DEPTH, RetrievalResult
from api.stores.doc_store import DocStore
from api.stores.graph_store import GraphStore
from api.stores.local.networkx_graph import NetworkXGraphStore
from api.stores.local.numpy_vector import NumpyVectorStore
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from api.stores.vector_store import VectorStore
from api.vault.compile import carried_claims, compile_vault, corpus_fingerprint
from api.vault.local import JsonVaultStore
from api.vault.store import VaultStore
from api.vault.types import Vault


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
    vault_store: VaultStore
    learner_store: LearnerStore
    lab_store: LabStore
    lab_generator: LabGenerator | None
    """The lab generator (D-36). The fake, in fake mode; None in a live mode until the live generator exists (V9): a lab is then refused, never faked."""
    _vault_lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    """One vault compile at a time: two requests that both find it stale reuse the first one's build (the check is made again inside)."""

    @property
    def ingest_deps(self) -> IngestDeps:
        return IngestDeps(
            docs=self.docs,
            vectors=self.vectors,
            graph=self.graph,
            embedder=self.embedder,
            llm=self.llm,
        )

    def vault(self) -> Vault | None:
        """The compiled vault of the stored documents, or None if none has been built (D-35)."""
        return self.vault_store.vault()

    def fresh_vault(self) -> Vault | None:
        with self._vault_lock:
            return self._fresh_vault()

    def _fresh_vault(self) -> Vault | None:
        """The vault, compiled again first if the stored documents or graph have changed since it was built (compounding: a document
        added or replaced reaches the notes view without anyone asking). A vault built before the corpus was recorded is kept as it
        is (until `POST /vault/rebuild`), and a missing vault is built only when documents are stored. If every document is later
        removed, the vault is rebuilt empty."""
        current = self.vault_store.vault()
        if current is None:
            return self._rebuild_vault() if self.docs.all_chunks() else None
        recorded = current.stats.get("corpus")
        if recorded is not None and recorded != corpus_fingerprint(self.graph, self.docs):
            return self._rebuild_vault()
        return current

    def rebuild_vault(self) -> Vault:
        with self._vault_lock:
            return self._rebuild_vault()

    def _rebuild_vault(self) -> Vault:
        """Compile the vault from the stored graph and passages and keep it. Deterministic, no model call. A previous build's
        claims are kept only if the build supplied them elsewhere: the a claim of a deleted passage is dropped by the compiler."""
        built = compile_vault(self.graph, self.docs, carried_claims(self.vault_store.vault()))
        self.vault_store.put_vault(built)
        self.vault_store.save()
        return built

    async def retrieve(self, query: str) -> RetrievalResult:
        """The evidence path: all three signals, fused (the `hybrid` arm)."""
        return await hybrid_retrieve(
            query,
            dense=DenseRetriever(vectors=self.vectors, docs=self.docs, embedder=self.embedder),
            sparse=SparseRetriever(docs=self.docs),
            graph=GraphRetriever(graph=self.graph, docs=self.docs),
            depth=CANDIDATE_DEPTH,
        )


def build_container(settings: Settings) -> Container:
    ensure_builtin_registered()  # a template whose validator has a hole stops the application starting (D-31)
    data = settings.arcana_data_dir
    data.mkdir(parents=True, exist_ok=True)
    engine = make_engine(data / "arcana.db")
    live = "live" in (settings.arcana_llm_mode, settings.arcana_embed_mode)
    ledger_path = settings.arcana_ledger_path or (Path("./data") / "ledger.db" if live else None)
    # In a live mode the ledger is one fixed file, not part of a data directory: the monthly cap must cover
    # every run (the API, the eval, a different --data-dir), and deleting a data directory to start clean
    # must not erase the spend history. Fake mode keeps it beside the data, so tests stay isolated.
    ledger_engine = make_engine(ledger_path) if ledger_path else engine
    ledger = SpendLedger(ledger_engine, settings.llm_monthly_cap_usd)
    lab_store = SqliteLabStore(data / "labs.db")
    docs_store = SqliteDocStore(engine)
    llm_service = build_llm_service(settings, ledger, fake_responder=fake_llm_responder)
    lab_generator: LabGenerator = (
        FakeLabGenerator() if settings.arcana_llm_mode == "fake" else LiveLabGenerator(llm_service, docs_store)
    )
    lab_store.mark_stale(  # P4b (D-41): a lab made under another template, contract or generator is not served until re-verified
        TEMPLATE_VERSION,
        {cid: contract_sha256(make()) for cid, make in CONTRACTS.items()},
        lab_generator.generator_id,
    )
    return Container(
        settings=settings,
        engine=engine,
        docs=docs_store,
        vectors=NumpyVectorStore(data / "vectors.npz"),
        graph=NetworkXGraphStore(data / "graph.json"),
        ledger=ledger,
        llm=llm_service,
        embedder=build_embedder(settings, ledger),
        uploads_dir=data / "uploads",
        vault_store=JsonVaultStore(data / "vault.json"),
        learner_store=SqliteLearnerStore(data / "learner.db"),
        lab_store=lab_store,
        lab_generator=lab_generator,
    )
