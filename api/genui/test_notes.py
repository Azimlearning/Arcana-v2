"""The notes components (M2.6): `ConceptPage` and `NotesGraph`, derived from the vault and checked by deriving them again.

Expected values are worked out by hand from the handmade world of `api/vault/test_compile.py` (see its header). For the page "rag"
(the long form and the abbreviation, two members):
    passages c1 and c3, in two documents; one definition (the sentence of c1 that defines RAG);
    links: the asserted `self_rag extends rag` has no stored sentence, so it is not shown and is counted as left out; the
    co-mention with "large language models" in c3 is shown with its sentence;
    mentions: one sentence from each document, c1 then c3 (passages in turn from each document).
"""

import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.agents.compose import compose_notes
from api.core.errors import NotFound, ValidationFailed
from api.core.settings import Settings
from api.genui.builders import concept_page, notes_graph
from api.genui.notes_catalog import CONCEPT_PAGE, NOTES_CATALOG, NOTES_GRAPH
from api.genui.validate import validate_block
from api.main import create_app
from api.vault.compile import compile_vault
from api.vault.test_compile import world
from api.vault.view import CAPS, derive_concept_page, derive_notes_graph

S1 = "Retrieval-Augmented Generation (RAG) is a method that combines retrieval with generation."
S3 = "Retrieval- augmented generation cuts it in large language models and RAG helps."


@pytest.fixture
def built(tmp_path: Path):
    graph, docs = world(tmp_path)
    return compile_vault(graph, docs), docs


def test_a_concept_page_is_derived_by_hand(built):
    vault, docs = built
    data = derive_concept_page(vault, docs, "rag")
    assert data is not None
    assert data["page"] == {"id": "rag", "label": "Retrieval-Augmented Generation"}
    assert (data["kind"], data["aliases"], data["passages"], data["documents"]) == (
        "concept",
        ["RAG"],
        2,
        2,
    )
    assert [c["id"] for c in data["citations"]] == [
        "c1",
        "c2",
    ]  # in the order they are first needed, one per (passage, quote)
    assert [(c["chunkId"], c["quote"]) for c in data["citations"]] == [
        ("c1", "Retrieval-Augmented Generation (RAG) combines retrieval with generation."),
        ("c3", S3),
    ]
    assert data["definitions"] == [{"citationId": "c1"}]
    assert data["links"] == [
        {
            "other": {"id": "large_language_model", "label": "large language models"},
            "kind": "co_mention",
            "relation": None,
            "direction": None,
            "citationId": "c2",
            "passages": 1,
        }
    ]
    assert data["linksLeftOut"] == 1  # the asserted extends link has no sentence to cite
    assert data["claims"] == [] and data["mentions"] == [{"citationId": "c1"}, {"citationId": "c2"}]
    assert data["mentionsLeftOut"] == 0


def test_an_asserted_link_is_shown_with_its_direction_and_comes_before_a_co_mention(built):
    vault, docs = built
    data = derive_concept_page(vault, docs, "self_rag")
    assert data is not None
    kinds = [(x["kind"], x["relation"], x["direction"], x["other"]["id"]) for x in data["links"]]
    assert kinds == [
        ("asserted", "uses", "out", "reflection_token"),
        ("co_mention", None, None, "reflection_token"),
    ]
    quote = {c["id"]: c["quote"] for c in data["citations"]}
    assert quote[data["links"][0]["citationId"]] == "Self-RAG uses reflection tokens."


def test_an_unknown_page_derives_nothing(built):
    vault, docs = built
    assert derive_concept_page(vault, docs, "ghost") is None
    assert derive_notes_graph(vault, docs, "ghost", "") is None


def test_the_overview_ranks_by_links_then_passages_and_a_query_narrows_it(built):
    vault, docs = built
    data = derive_notes_graph(vault, docs, None, "")
    assert data is not None and data["focusId"] is None and data["nodesLeftOut"] == 0
    # degrees: self_rag 2 (reflection_token, rag), rag 2 (self_rag, large_language_model), reflection_token 1,
    # large_language_model 1, people 0; ties by passages then id
    assert [n["id"] for n in data["nodes"]] == [
        "rag",
        "self_rag",
        "large_language_model",
        "reflection_token",
        "alice_smith",
        "bob_jones",
    ]
    assert {(e["source"], e["target"], e["kind"]) for e in data["edges"]} == {
        ("self_rag", "reflection_token", "asserted"),
        ("self_rag", "rag", "asserted"),
        ("large_language_model", "rag", "co_mention"),
        ("reflection_token", "self_rag", "co_mention"),
    }
    narrowed = derive_notes_graph(vault, docs, None, "  TOKENS ")
    assert (
        narrowed is not None
        and narrowed["query"] == "TOKENS"
        and [n["id"] for n in narrowed["nodes"]] == ["reflection_token"]
    )
    by_alias = derive_notes_graph(vault, docs, None, "rag")
    assert by_alias is not None and "rag" in [
        n["id"] for n in by_alias["nodes"]
    ]  # the alias "RAG" matches the page


def test_a_focused_graph_is_the_page_and_its_neighbours_strongest_first(built):
    vault, docs = built
    data = derive_notes_graph(vault, docs, "self_rag", "")
    assert data is not None and data["focusId"] == "self_rag"
    assert [n["id"] for n in data["nodes"]] == [
        "self_rag",
        "rag",
        "reflection_token",
    ]  # both asserted and equally strong: the page in more passages first
    assert (
        data["nodesLeftOut"] == 0 and len(data["edges"]) == 3
    )  # two asserted, one co-mention among the three


def block_of(vault, docs, page="rag"):
    return concept_page(f"page:{page}", "ready", data=derive_concept_page(vault, docs, page))


def test_a_derived_page_and_graph_pass_the_validator(built):
    vault, docs = built
    assert validate_block(block_of(vault, docs), docs, vault=vault).type == "ConceptPage"
    graph = notes_graph("notes-graph", "ready", data=derive_notes_graph(vault, docs, None, ""))
    assert validate_block(graph, docs, vault=vault).type == "NotesGraph"


def test_the_notes_blocks_are_refused_without_the_vault_they_are_checked_against(built):
    vault, docs = built
    with pytest.raises(ValidationFailed, match="content validation"):
        validate_block(block_of(vault, docs), docs)
    with pytest.raises(ValidationFailed):
        validate_block(
            notes_graph("g", "ready", data=derive_notes_graph(vault, docs, None, "")), docs
        )


def _page_defects():
    def drop_link(d):
        d["links"].pop()

    def add_link(d):
        d["links"].append(copy.deepcopy(d["links"][0]))

    def wrong_label(d):
        d["page"]["label"] = "Something Else"

    def wrong_id(d):
        d["page"]["id"] = "ghost"

    def counts(d):
        d["passages"] = 3

    def documents(d):
        d["documents"] = 1

    def alias(d):
        d["aliases"].append("Invented")

    def kind(d):
        d["kind"] = "method"

    def link_kind(d):
        d["links"][0]["kind"] = "asserted"

    def link_relation(d):
        d["links"][0]["relation"] = "uses"

    def link_other(d):
        d["links"][0]["other"]["label"] = "Other"

    def left_out(d):
        d["linksLeftOut"] = 0

    def definition(d):
        d["definitions"] = []

    def mention(d):
        d["mentions"].reverse()

    def left_mentions(d):
        d["mentionsLeftOut"] = 5

    def quote(d):
        d["citations"][0]["quote"] = "A sentence that the passage never says."

    def title(d):
        d["citations"][0]["docTitle"] = "Another title"

    def chunk(d):
        d["citations"][1]["chunkId"] = "nowhere"

    def orphan(d):
        d["citations"].append({**d["citations"][0], "id": "c9"})

    def claim(d):
        d["claims"].append(
            {
                "citationId": "c1",
                "pages": [{"id": "rag", "label": "Retrieval-Augmented Generation"}],
            }
        )

    return [
        drop_link,
        add_link,
        wrong_label,
        wrong_id,
        counts,
        documents,
        alias,
        kind,
        link_kind,
        link_relation,
        link_other,
        left_out,
        definition,
        mention,
        left_mentions,
        quote,
        title,
        chunk,
        orphan,
        claim,
    ]


@pytest.mark.parametrize("defect", _page_defects(), ids=lambda f: f.__name__)
def test_the_page_validator_rejects_every_planted_defect(built, defect):
    vault, docs = built
    raw = block_of(vault, docs)
    defect(raw["data"])
    with pytest.raises(ValidationFailed) as refused:
        validate_block(raw, docs, vault=vault)
    assert refused.value.issues, "a refusal names the field"


def _graph_defects():
    def drop_node(d):
        d["nodes"].pop()

    def extra_node(d):
        d["nodes"].append({**d["nodes"][0], "id": "ghost"})

    def drop_edge(d):
        d["edges"].pop()

    def kind(d):
        d["edges"][0]["kind"] = "co_mention" if d["edges"][0]["kind"] == "asserted" else "asserted"

    def strength(d):
        d["edges"][0]["passages"] += 1

    def left_out(d):
        d["nodesLeftOut"] = 3

    def label(d):
        d["nodes"][0]["label"] = "x"

    def degree(d):
        d["nodes"][0]["degree"] += 1

    def query(d):
        d["query"] = "tokens"

    def focus(d):
        d["focusId"] = "ghost"

    def order(d):
        d["nodes"].reverse()

    return [
        drop_node,
        extra_node,
        drop_edge,
        kind,
        strength,
        left_out,
        label,
        degree,
        query,
        focus,
        order,
    ]


@pytest.mark.parametrize("defect", _graph_defects(), ids=lambda f: f.__name__)
def test_the_graph_validator_rejects_every_planted_defect(built, defect):
    vault, docs = built
    raw = notes_graph("notes-graph", "ready", data=derive_notes_graph(vault, docs, None, ""))
    defect(raw["data"])
    with pytest.raises(ValidationFailed):
        validate_block(raw, docs, vault=vault)


def test_placeholders_carry_nothing_and_a_ready_graph_needs_a_page(built):
    vault, docs = built
    for status in ("empty", "loading"):
        assert validate_block(concept_page("p", status), docs, vault=vault).meta.status == status
        assert validate_block(notes_graph("g", status), docs, vault=vault).meta.status == status
    full = block_of(vault, docs)
    full["meta"]["status"] = "empty"
    with pytest.raises(ValidationFailed, match="content validation"):
        validate_block(full, docs, vault=vault)
    with pytest.raises(ValidationFailed):
        validate_block(notes_graph("g", "ready"), docs, vault=vault)  # ready with nothing to show


def test_compose_notes_places_the_page_in_chat_and_the_graph_in_the_studio(built):
    vault, docs = built
    layout, blocks = compose_notes(vault, docs, "self_rag", "")
    assert [(b.type, b.id) for b in blocks] == [
        ("ConceptPage", "page:self_rag"),
        ("NotesGraph", "notes-graph"),
    ]
    where = {p.blockId: (p.panel, p.region) for p in layout.placements}
    assert where == {"page:self_rag": ("chat", "main"), "notes-graph": ("studio", "main")}
    overview_layout, overview = compose_notes(vault, docs, None, "")
    assert [b.type for b in overview] == ["NotesGraph"] and overview_layout.placements[
        0
    ].panel == "studio"


def test_compose_notes_with_no_vault_or_an_unknown_page_or_no_match(built):
    vault, docs = built
    _, blocks = compose_notes(None, docs, None, "tokens")
    assert [(b.type, b.meta.status) for b in blocks] == [("NotesGraph", "empty")]
    with pytest.raises(NotFound):
        compose_notes(vault, docs, "ghost", "")
    _, blocks = compose_notes(vault, docs, None, "no such concept anywhere")
    assert [(b.type, b.meta.status) for b in blocks] == [("NotesGraph", "empty")]
    assert blocks[0].data.query == "no such concept anywhere"  # type: ignore[union-attr]


def test_the_notes_specs_state_their_precondition_fences_and_placement_and_the_guide_says_the_same_numbers():
    guide = (Path(__file__).resolve().parents[2] / "refdocs" / "guides" / "catalog.md").read_text(
        encoding="utf-8"
    )
    assert set(NOTES_CATALOG) == {"ConceptPage", "NotesGraph", "QuizCard", "StudySet", "StudyPlan", "DocBrief"}
    for spec in NOTES_CATALOG.values():
        assert (
            spec.precondition.strip()
            and spec.supplied_by == ("vault",)
            and spec.fences.grounding == "vault_rederived"
        )
        caps = " ".join(f"{k}={v}" for k, v in spec.caps.items())
        assert f"caps `{caps}`" in guide, f"catalog.md does not state {spec.name}'s caps: {caps}"
        for requirement in spec.fences.a11y:
            assert f"{requirement.role}:{requirement.label}" in guide
    assert CONCEPT_PAGE.placement.panel == "chat" and NOTES_GRAPH.placement.panel == "studio"
    assert (
        CONCEPT_PAGE.caps["links"] == CAPS["links"] and NOTES_GRAPH.caps["nodes"] == CAPS["nodes"]
    )


# ── over HTTP, on a real ingest with fakes ────────────────────────────────────


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(_env_file=None, arcana_data_dir=tmp_path / "data")  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as c:
        yield c


def test_the_notes_route_is_empty_before_a_vault_exists_and_serves_a_validated_view_after_a_rebuild(
    client, pdf_bytes
):
    first = client.get("/vault/notes")
    assert first.status_code == 200 and [b["meta"]["status"] for b in first.json()["blocks"]] == [
        "empty"
    ]
    assert (
        client.post(
            "/ingest", files={"file": ("hybrid_retrieval.pdf", pdf_bytes, "application/pdf")}
        ).status_code
        == 200
    )
    rebuilt = client.post("/vault/rebuild")
    assert rebuilt.status_code == 200 and rebuilt.json()["pages"] > 0
    overview = client.get("/vault/notes").json()
    graph = overview["blocks"][0]
    assert (
        graph["type"] == "NotesGraph"
        and graph["meta"]["status"] == "ready"
        and graph["data"]["nodes"]
    )
    page_id = graph["data"]["nodes"][0]["id"]
    focused = client.get("/vault/notes", params={"page": page_id}).json()
    assert [b["type"] for b in focused["blocks"]] == ["ConceptPage", "NotesGraph"]
    assert (
        focused["blocks"][0]["data"]["page"]["id"] == page_id
        and focused["blocks"][0]["data"]["citations"]
    )
    assert {p["panel"] for p in focused["layout"]["placements"]} == {"chat", "studio"}


def test_the_notes_route_answers_an_unknown_page_with_an_error_envelope_and_a_long_query_with_a_validation_error(
    client, pdf_bytes
):
    client.post("/ingest", files={"file": ("hybrid_retrieval.pdf", pdf_bytes, "application/pdf")})
    client.post("/vault/rebuild")
    missing = client.get("/vault/notes", params={"page": "no_such_page"})
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"
    long = client.get("/vault/notes", params={"query": "x" * 500})
    assert long.status_code == 422 and long.json()["code"] == "validation_failed"


# ── the caps, the label limit, the precondition and the accessibility labels (schema-guardian, M2.6) ───────────────────


def _crowded_world(tmp_path: Path):
    """One hub page in 45 passages, stated links to 45 pages (45 sentences), 12 claims, 10 definitions, and 190 links among the
    first 20 other pages (so a graph of 40 pages has more than the 120-edge cap)."""
    from api.stores.doc_store import Chunk, Document
    from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
    from api.vault.types import ClaimNote, ConceptPage, Definition, PageLink, Vault

    docs = SqliteDocStore(make_engine(tmp_path / "crowd.db"))
    docs.put_document(Document("d", "T", "t.pdf", "ready", 1, None, "2026-10-07"))
    sentences = [f"Hub relates to Other{i} in this sentence number {i}." for i in range(45)]
    docs.put_chunks([Chunk(f"c{i}", "d", i, 1, s) for i, s in enumerate(sentences)])
    pages = {
        "hub": ConceptPage(
            "hub",
            "Hub",
            (),
            ("hub",),
            "concept",
            ("d",),
            tuple(f"c{i}" for i in range(45)),
            tuple(Definition(sentences[i], f"c{i}", "d") for i in range(10)),
        )
    }
    for i in range(45):
        pages[f"o{i:02d}"] = ConceptPage(
            f"o{i:02d}", f"Other{i}", (), (f"o{i:02d}",), None, ("d",), (f"c{i}",), ()
        )
    links = [
        PageLink("hub", f"o{i:02d}", "asserted", "uses", (f"c{i}",), sentences[i])
        for i in range(45)
    ]
    links += [
        PageLink(f"o{i:02d}", f"o{j:02d}", "co_mention", None, (f"c{i}",), sentences[i])
        for i in range(20)
        for j in range(i + 1, 20)
    ]
    claims = [ClaimNote(f"claim-{i}", f"c{i}", "d", sentences[i], ("hub",)) for i in range(12)]
    return Vault("vault-1", 45, pages, links, claims), docs


def test_every_cap_is_enforced_and_what_is_left_out_is_counted(tmp_path: Path):
    vault, docs = _crowded_world(tmp_path)
    page = derive_concept_page(vault, docs, "hub")
    assert page is not None
    assert (len(page["definitions"]), len(page["links"]), page["linksLeftOut"]) == (
        CAPS["definitions"],
        CAPS["links"],
        5,
    )
    assert len(page["claims"]) == CAPS["claims"] and len(page["mentions"]) == CAPS["mentions"]
    assert page["mentionsLeftOut"] == 45 - CAPS["mentions"] and page["passages"] == 45
    assert (
        validate_block(concept_page("page:hub", "ready", data=page), docs, vault=vault).type
        == "ConceptPage"
    )

    focused = derive_notes_graph(vault, docs, "hub", "")
    assert (
        focused is not None
        and len(focused["nodes"]) == CAPS["nodes"]
        and focused["nodesLeftOut"] == 45 - (CAPS["nodes"] - 1)
    )
    overview = derive_notes_graph(vault, docs, None, "")
    assert (
        overview is not None
        and len(overview["nodes"]) == CAPS["nodes"]
        and overview["nodesLeftOut"] == 46 - CAPS["nodes"]
    )
    assert (
        len(overview["edges"]) == CAPS["edges"]
    )  # more than 120 links among the 40 pages: the first 120, strongest kind first
    assert overview["edges"][0]["kind"] == "asserted"
    assert (
        validate_block(notes_graph("notes-graph", "ready", data=overview), docs, vault=vault).type
        == "NotesGraph"
    )


def test_a_very_long_page_name_is_cut_at_the_label_limit_and_the_block_still_validates(
    tmp_path: Path,
):
    vault, docs = _crowded_world(tmp_path)
    long = " ".join(["Word"] * 80)
    vault.pages["hub"] = vault.pages["hub"].__class__(
        "hub",
        long,
        (long,),
        ("hub",),
        "concept",
        ("d",),
        vault.pages["hub"].mention_chunk_ids,
        vault.pages["hub"].definitions,
    )
    page = derive_concept_page(vault, docs, "hub")
    assert (
        page is not None
        and len(page["page"]["label"]) <= CAPS["label_chars"]
        and not page["page"]["label"].endswith(" ")
    )
    assert all(len(a) <= CAPS["label_chars"] for a in page["aliases"])
    assert (
        validate_block(concept_page("page:hub", "ready", data=page), docs, vault=vault).type
        == "ConceptPage"
    )
    graph = derive_notes_graph(vault, docs, None, "")
    assert graph is not None and all(len(n["label"]) <= CAPS["label_chars"] for n in graph["nodes"])


def test_a_ready_page_needs_a_passage_that_mentions_it(tmp_path: Path):
    from api.vault.types import ConceptPage, Vault

    _, docs = _crowded_world(tmp_path)
    stale = Vault(
        "vault-1",
        45,
        {"ghost": ConceptPage("ghost", "Ghost", (), ("ghost",), None, (), (), ())},
        [],
    )
    data = derive_concept_page(stale, docs, "ghost")  # a vault whose passages are gone
    assert data is not None and data["passages"] == 0
    with pytest.raises(ValidationFailed) as refused:
        validate_block(concept_page("page:ghost", "ready", data=data), docs, vault=stale)
    assert refused.value.issues[0].path == "data.passages"


def test_the_notes_components_expose_the_roles_and_labels_their_fences_require():
    """A static check against each component's source, as for the turn components (the component tests assert them at run time)."""
    root = Path(__file__).resolve().parents[2] / "web" / "components" / "genui"
    for name, spec in NOTES_CATALOG.items():
        source = (root / f"{name}.tsx").read_text(encoding="utf-8")
        for requirement in spec.fences.a11y:
            assert requirement.label in source, (
                f"{name}: no {requirement.role} labelled {requirement.label!r}"
            )
