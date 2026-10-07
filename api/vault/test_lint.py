"""Vault lint and compounding (M2.8): every expected list is worked out by hand from the handmade vault below.

Eight passages. Pages (id: name, passages that mention it):
    large_language_model: "large language models" c1 c2 c3, defined in two papers
    language_model: "language models" c2          llm: "LLM" c1
    dense_retrieval: "dense retrieval" c4         dense_retrievals: "Dense Retrievals" c5
    rag: "RAG" c1 c2                              banana: "banana" c6
Links: large_language_model -- language_model (co-mention), rag -- large_language_model (asserted).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.core.settings import Settings
from api.main import create_app
from api.stores.doc_store import Document
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from api.vault.compile import compile_vault, corpus_fingerprint
from api.vault.lint import DISPLAY_CAP, duplicates, hubs, lint, orphans, tensions
from api.vault.test_compile import world
from api.vault.types import ConceptPage, Definition, PageLink, Vault


def page(
    pid: str, label: str, mentions: tuple[str, ...], definitions: tuple[Definition, ...] = ()
) -> ConceptPage:
    return ConceptPage(pid, label, (), (pid,), None, ("d1",), mentions, definitions)


@pytest.fixture
def small(tmp_path: Path):
    docs = SqliteDocStore(make_engine(tmp_path / "lint.db"))
    for d, title in (("d1", "Paper One"), ("d2", "Paper Two")):
        docs.put_document(Document(d, title, f"{d}.pdf", "ready", 1, None, "2026-10-07"))
    pages = [
        page(
            "large_language_model",
            "large language models",
            ("c1", "c2", "c3"),
            (
                Definition(
                    "Large language models are neural networks trained on text.", "c1", "d1"
                ),
                Definition("A large language model predicts the next token.", "c3", "d2"),
            ),
        ),
        page("language_model", "language models", ("c2",)),
        page("llm", "LLM", ("c1",)),
        page("dense_retrieval", "dense retrieval", ("c4",)),
        page("dense_retrievals", "Dense Retrievals", ("c5",)),
        page("rag", "RAG", ("c1", "c2")),
        page("banana", "banana", ("c6",)),
    ]
    links = [
        PageLink("language_model", "large_language_model", "co_mention", None, ("c2",), "s"),
        PageLink("large_language_model", "rag", "asserted", "uses", ("c1",), "s"),
    ]
    return Vault("vault-1", 8, {p.id: p for p in pages}, links), docs


def test_orphans_are_the_mentioned_pages_no_link_reaches(small):
    vault, _ = small
    # one passage each, so the order is by id; llm, the dense pages and banana have no link; rag and the model pages do
    assert [p.id for p in orphans(vault)] == [
        "banana",
        "dense_retrieval",
        "dense_retrievals",
        "llm",
    ]
    unmentioned = Vault("vault-1", 8, {"ghost": page("ghost", "Ghost", ())}, [])
    assert orphans(unmentioned) == []  # a page nothing mentions is not an orphan, it is empty


def test_hubs_are_pages_a_quarter_of_the_passages_mention(small):
    vault, _ = small
    assert [p.id for p in hubs(vault)] == [
        "large_language_model",
        "rag",
    ]  # 3 and 2 of 8 passages: 0.375 and 0.25
    assert hubs(Vault("vault-1", 0, {}, [])) == []


def test_near_duplicates_by_name_are_listed_with_their_reason_and_never_merged(small):
    vault, _ = small
    pairs = [(a.id, b.id, reason) for a, b, reason in duplicates(vault)]
    assert pairs == [
        (
            "dense_retrieval",
            "dense_retrievals",
            "same_name",
        ),  # the same words after folding the plural
        ("language_model", "large_language_model", "one_more_word"),
        ("large_language_model", "llm", "initials"),  # L, L, M
    ]
    assert len(vault.pages) == 7  # lint changed nothing


def test_a_concept_two_papers_define_is_listed_with_each_papers_title_and_definition(small):
    vault, docs = small
    found = tensions(vault, docs)
    assert [p.id for p, _ in found] == ["large_language_model"]
    assert found[0][1] == [
        {
            "docTitle": "Paper One",
            "text": "Large language models are neural networks trained on text.",
        },
        {"docTitle": "Paper Two", "text": "A large language model predicts the next token."},
    ]


def test_the_report_has_the_shape_of_the_wire_type_and_exact_totals(small):
    from api.genui.generated import VaultLintResponse

    vault, docs = small
    report = lint(vault, docs)
    parsed = VaultLintResponse.model_validate(
        report
    )  # strict: a key or type that drifts fails here
    assert (parsed.pages, parsed.orphansTotal, parsed.duplicatesTotal, parsed.tensionsTotal) == (
        7,
        4,
        3,
        1,
    )
    assert (
        parsed.duplicates[0].reason == "one_more_word"
    )  # the pair with the most passages first (3 + 1)
    assert [h.id for h in parsed.hubs] == ["large_language_model", "rag"]


def test_lists_are_capped_for_display_but_the_totals_are_exact(tmp_path: Path):
    docs = SqliteDocStore(make_engine(tmp_path / "many.db"))
    pages = {
        f"p{i:03d}": page(f"p{i:03d}", f"alpha{i}x beta{i}y", (f"c{i}",))
        for i in range(DISPLAY_CAP + 20)
    }
    report = lint(Vault("vault-1", 500, pages, []), docs)
    assert len(report["orphans"]) == DISPLAY_CAP and report["orphansTotal"] == DISPLAY_CAP + 20


def test_pages_with_different_words_make_no_pair():
    pages = {f"p{i:03d}": page(f"p{i:03d}", f"model{i}z", ("c1",)) for i in range(5)}
    assert duplicates(Vault("vault-1", 5, pages, [])) == []  # different words: no pair


# ── compounding: the vault follows the stored documents ───────────────────────


def test_the_corpus_fingerprint_changes_with_a_passage_or_the_graph_and_not_otherwise(
    tmp_path: Path,
):
    graph, docs = world(tmp_path)
    first = corpus_fingerprint(graph, docs)
    assert corpus_fingerprint(graph, docs) == first
    assert compile_vault(graph, docs).stats["corpus"] == first
    from api.stores.graph_store import Node

    graph.upsert_node(Node("new_concept", "new concept", None, ("d1",), ("c1",), None, None))
    assert corpus_fingerprint(graph, docs) != first


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(_env_file=None, arcana_data_dir=tmp_path / "data")  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as c:
        yield c


def _second_pdf(tmp_path: Path, monkeypatch) -> bytes:
    from api.tests.fixtures import make_fixture_pdf

    monkeypatch.setattr(make_fixture_pdf, "TITLE", "A Second Paper on Reranking")
    monkeypatch.setattr(
        make_fixture_pdf,
        "PAGES",
        [
            "Second Paper. Cross Encoders rerank passages that Dense Retrieval returns. Cross Encoders are slow but exact."
        ],
    )
    path = tmp_path / "second.pdf"
    make_fixture_pdf.build(path)
    return path.read_bytes()


def test_a_document_added_later_reaches_the_notes_view_without_anyone_rebuilding(
    client, pdf_bytes, tmp_path, monkeypatch
):
    assert (
        client.get("/vault/notes").json()["blocks"][0]["meta"]["status"] == "empty"
    )  # nothing stored yet
    client.post("/ingest", files={"file": ("one.pdf", pdf_bytes, "application/pdf")})
    first = client.get("/vault/notes").json()["blocks"][0][
        "data"
    ]  # the vault is built on first use
    labels = {n["label"] for n in first["nodes"]}
    assert first["nodes"] and "Cross Encoders" not in labels
    client.post(
        "/ingest",
        files={"file": ("two.pdf", _second_pdf(tmp_path, monkeypatch), "application/pdf")},
    )
    second = client.get("/vault/notes", params={"query": "cross"}).json()["blocks"][0]["data"]
    assert "Cross Encoders" in {
        n["label"] for n in second["nodes"]
    }  # the new document's concept is there, with no rebuild call


def test_the_vault_after_adding_a_document_equals_one_compiled_from_scratch(
    client, pdf_bytes, tmp_path, monkeypatch
):
    client.post("/ingest", files={"file": ("one.pdf", pdf_bytes, "application/pdf")})
    client.get("/vault/notes")
    client.post(
        "/ingest",
        files={"file": ("two.pdf", _second_pdf(tmp_path, monkeypatch), "application/pdf")},
    )
    container = client.app.state.container  # type: ignore[attr-defined]
    kept = container.fresh_vault()
    assert (
        kept is not None
        and kept.sha256() == compile_vault(container.graph, container.docs).sha256()
    )
    assert (
        container.fresh_vault() is container.fresh_vault()
    )  # nothing changed: it is kept, not rebuilt again


def test_a_vault_built_before_fingerprints_existed_is_kept_as_it_is(client, pdf_bytes):
    client.post("/ingest", files={"file": ("one.pdf", pdf_bytes, "application/pdf")})
    container = client.app.state.container  # type: ignore[attr-defined]
    built = container.rebuild_vault()
    built.stats.pop("corpus")
    container.vault_store.put_vault(built)
    assert container.fresh_vault() is built


def test_the_lint_route_answers_with_a_validated_report_and_an_empty_one_before_any_vault(
    client, pdf_bytes
):
    empty = client.get("/vault/lint")
    assert empty.status_code == 200 and empty.json()["pages"] == 0 and empty.json()["orphans"] == []
    client.post("/ingest", files={"file": ("one.pdf", pdf_bytes, "application/pdf")})
    report = client.get("/vault/lint").json()
    assert report["pages"] > 0 and set(report) == {
        "pages",
        "orphans",
        "orphansTotal",
        "duplicates",
        "duplicatesTotal",
        "tensions",
        "tensionsTotal",
        "hubs",
    }


# ── what the schema-guardian found (M2.7, M2.8) ───────────────────────────────


def test_two_requests_that_both_find_the_vault_stale_compile_it_once(client, pdf_bytes):
    import threading
    import time

    client.post("/ingest", files={"file": ("one.pdf", pdf_bytes, "application/pdf")})
    container = client.app.state.container  # type: ignore[attr-defined]
    built = {"count": 0}
    real = container._rebuild_vault

    def counting():
        built["count"] += 1
        time.sleep(0.2)  # long enough for the second thread to arrive while the first is compiling
        return real()

    container._rebuild_vault = counting
    results: list = []
    threads = [
        threading.Thread(target=lambda: results.append(container.fresh_vault())) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert built["count"] == 1 and len(results) == 4 and all(r is not None for r in results)
    assert len({r.sha256() for r in results if r is not None}) == 1


def test_a_damaged_vault_file_is_no_vault_and_saving_leaves_no_temp_file(tmp_path: Path):
    from api.vault.local import JsonVaultStore

    path = tmp_path / "vault.json"
    path.write_text(
        '{"vault": {"version": "vault-1", "n_chunks": 3', encoding="utf-8"
    )  # cut off mid-write
    store = JsonVaultStore(path)
    assert store.vault() is None  # derived data: compiled again, never a start-up failure
    graph, docs = world(tmp_path)
    store.put_vault(compile_vault(graph, docs))
    store.save()
    store.save()
    assert JsonVaultStore(path).vault() is not None and not list(tmp_path.glob("*.tmp"))
    path.write_text("[]", encoding="utf-8")
    assert JsonVaultStore(path).vault() is None  # the wrong shape is damage too


def test_the_graph_can_be_read_from_another_thread_while_ingestion_adds_to_it(tmp_path: Path):
    import threading

    from api.stores.graph_store import Node
    from api.stores.local.networkx_graph import NetworkXGraphStore

    graph = NetworkXGraphStore(tmp_path / "g.json")
    for i in range(50):
        graph.upsert_node(Node(f"seed{i}", f"seed{i}", None, ("d",), ("c",), None, None))
    errors: list[BaseException] = []
    stop = threading.Event()

    def reader():
        try:
            while not stop.is_set():
                graph.nodes()
                graph.edges()
        except BaseException as exc:
            errors.append(exc)

    readers = [threading.Thread(target=reader) for _ in range(3)]
    for t in readers:
        t.start()
    for i in range(2000):
        graph.upsert_node(Node(f"n{i}", f"n{i}", None, ("d",), ("c",), None, None))
    stop.set()
    for t in readers:
        t.join()
    assert errors == [] and len(graph.nodes()) == 2050


def test_the_fingerprint_sees_a_node_kind_a_note_and_a_passage_position(tmp_path: Path):
    from api.stores.graph_store import Node
    from api.stores.local.networkx_graph import NetworkXGraphStore

    def graph_with(kind, note, d):
        g = NetworkXGraphStore(d / "g.json")
        g.upsert_node(Node("a", "alpha concept", "t", ("d1",), ("c1",), kind, note))
        return g

    base = tmp_path / "base"
    base.mkdir()
    _, docs = world(base)
    first = corpus_fingerprint(graph_with("method", "A sentence about alpha concept.", base), docs)
    other = tmp_path / "other"
    other.mkdir()
    assert (
        corpus_fingerprint(graph_with("model", "A sentence about alpha concept.", other), docs)
        != first
    )  # a kind
    third = tmp_path / "third"
    third.mkdir()
    assert (
        corpus_fingerprint(
            graph_with("method", "Another sentence about alpha concept.", third), docs
        )
        != first
    )  # a note


def test_a_learner_file_that_cannot_be_read_does_not_take_the_notes_view_down(tmp_path: Path):
    from api.agents.compose import compose_notes

    graph, docs = world(tmp_path)
    vault = compile_vault(graph, docs)

    class Broken:
        def mastery(self, page_ids, now=None):
            raise RuntimeError("database is locked")

    _, blocks = compose_notes(vault, docs, "rag", "", Broken())  # type: ignore[arg-type]
    assert [b.type for b in blocks] == ["ConceptPage", "NotesGraph"] and blocks[
        0
    ].data.mastery is None  # type: ignore[union-attr]


def test_a_rating_request_with_a_huge_body_is_refused_before_it_is_read(client):
    big = client.post(
        "/learner/events", content=b"x" * 10_000, headers={"Content-Type": "application/json"}
    )
    assert big.status_code == 413
    long_id = "p" * 3000
    refused = client.post("/learner/events", json={"pageId": long_id, "signal": "know"})
    assert (
        refused.status_code == 404 and long_id not in refused.text
    )  # the id is cut in the message, not echoed whole
