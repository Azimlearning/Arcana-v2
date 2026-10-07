"""The vault retriever `vault-1` (M2.2): every score below is computed by hand from the handmade vault.

Six passages in one document, in order c1..c6; N = 6.
    pages     alpha mentioned in c1 c2          (df 2)     beta  in c2 c3 c4  (df 3)
              gamma in c5                       (df 1)     delta in c6        (df 1)
              "beta" has a second member id, `beta_two`, that the frozen resolver also reads.
    links     asserted alpha -> beta, evidence from c3          co-mention beta -- gamma, in c4
    claim     a claim naming gamma sits in c6
    spread    idf(df) = ln(1 + 6/df) / ln(7)
"""

import math
from pathlib import Path

import pytest

from api.ingestion.embed import Embedder
from api.retrieval.vault import (
    ASSERTED_NEIGHBOUR_WEIGHT,
    CLAIM_WEIGHT,
    CO_MENTION_NEIGHBOUR_WEIGHT,
    SEMANTIC_WEIGHT,
    VaultRetriever,
    embed_page_labels,
)
from api.stores.doc_store import Chunk, Document
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from api.vault.types import ClaimNote, ConceptPage, PageLink, Vault

N = 6


def idf(df: int) -> float:
    return math.log(1 + N / df) / math.log(1 + N)


def page(
    pid: str,
    mentions: tuple[str, ...],
    nodes: tuple[str, ...] | None = None,
    label: str | None = None,
) -> ConceptPage:
    return ConceptPage(pid, label or pid, (), nodes or (pid,), None, ("d",), mentions, ())


def vault(*, claims: bool = True) -> Vault:
    pages = {
        "alpha": page("alpha", ("c1", "c2")),
        "beta": page("beta", ("c2", "c3", "c4"), ("beta", "beta_two")),
        "gamma": page("gamma", ("c5",)),
        "delta": page("delta", ("c6",)),
    }
    links = [
        PageLink("alpha", "beta", "asserted", "uses", ("c3",), "evidence"),
        PageLink("beta", "gamma", "co_mention", None, ("c4",), "a sentence"),
    ]
    notes = [ClaimNote("claim-1", "c6", "d", "A claim about gamma.", ("gamma",))] if claims else []
    return Vault("vault-1", N, pages, links, notes)


def docs(tmp_path: Path) -> SqliteDocStore:
    store = SqliteDocStore(make_engine(tmp_path / "v.db"))
    store.put_document(Document("d", "T", "t.pdf", "ready", 1, None, "2026-10-07"))
    store.put_chunks([Chunk(f"c{i}", "d", i, 1, f"text c{i}") for i in range(1, 7)])
    return store


def scored(result) -> list[tuple[str, float]]:
    return [(c.id, round(c.score, 9)) for c in result.chunks]


async def run(tmp_path: Path, query: str, **kwargs):
    kwargs.setdefault("vault", vault())
    return await VaultRetriever(docs=docs(tmp_path), **kwargs).retrieve(query)


async def test_a_page_scores_its_mentions_and_asserted_evidence_then_its_neighbours(tmp_path: Path):
    r = await run(tmp_path, "alpha")
    a, b = idf(2), idf(3)
    # direct: c1, c2 (mentions) and c3 (evidence of alpha -> beta); asserted neighbour beta adds c4 (c2, c3 already direct)
    # co-mention neighbours of alpha: none
    assert scored(r) == [
        (
            "c3",
            round(a, 9),
        ),  # tie with c1 and c2 at idf(alpha); support (the asserted link's evidence) puts c3 first
        ("c1", round(a, 9)),
        ("c2", round(a, 9)),
        ("c4", round(ASSERTED_NEIGHBOUR_WEIGHT * b, 9)),
    ]


async def test_a_co_mention_neighbour_counts_a_quarter_and_never_over_an_asserted_one(
    tmp_path: Path,
):
    r = await run(tmp_path, "beta")
    a, b, g = idf(2), idf(3), idf(1)
    # direct for beta: c2 c3 c4 (mentions) and c3 (evidence). asserted neighbour alpha: c1 (c2 already direct) = 0.5 * idf(alpha).
    # co-mention neighbour gamma: c5 = 0.25 * idf(gamma). The claim names gamma, which is not resolved: no claim score.
    assert scored(r) == [
        ("c3", round(b, 9)),
        ("c2", round(b, 9)),
        ("c4", round(b, 9)),
        ("c1", round(ASSERTED_NEIGHBOUR_WEIGHT * a, 9)),
        ("c5", round(CO_MENTION_NEIGHBOUR_WEIGHT * g, 9)),
    ]


async def test_any_member_node_id_of_a_page_resolves_to_the_page(tmp_path: Path):
    r = await run(tmp_path, "beta_two")
    assert r.resolution is not None
    assert [e.node_id for e in r.resolution.entities] == ["beta"]
    assert {c.id for c in r.chunks} == {"c1", "c2", "c3", "c4", "c5"}


async def test_two_members_of_one_page_in_a_question_resolve_once(tmp_path: Path):
    r = await run(tmp_path, "beta and beta_two")
    assert r.resolution is not None and [e.node_id for e in r.resolution.entities] == ["beta"]
    assert r.chunks[0].score == pytest.approx(idf(3))  # not double counted


async def test_the_spread_discount_can_be_switched_off(tmp_path: Path):
    r = await run(tmp_path, "alpha", spread=False)
    assert scored(r) == [("c3", 1.0), ("c1", 1.0), ("c2", 1.0), ("c4", 0.5)]


async def test_co_mention_links_can_be_switched_off(tmp_path: Path):
    r = await run(tmp_path, "beta", co_mentions=False)
    assert "c5" not in {c.id for c in r.chunks}
    assert {c.id for c in r.chunks} == {"c1", "c2", "c3", "c4"}


async def test_claims_add_a_quarter_to_the_passage_that_holds_one_about_a_resolved_page(
    tmp_path: Path,
):
    r = await run(tmp_path, "gamma")
    g, b = idf(1), idf(3)
    # direct: c5. co-mention neighbour beta: c2 c3 c4 = 0.25 * idf(beta). claim in c6 = 0.25 * idf(gamma).
    assert scored(r) == [
        ("c5", round(g, 9)),
        ("c6", round(CLAIM_WEIGHT * g, 9)),
        ("c2", round(CO_MENTION_NEIGHBOUR_WEIGHT * b, 9)),
        ("c3", round(CO_MENTION_NEIGHBOUR_WEIGHT * b, 9)),
        ("c4", round(CO_MENTION_NEIGHBOUR_WEIGHT * b, 9)),
    ]
    off = await run(tmp_path, "gamma", claims=False)
    assert "c6" not in {c.id for c in off.chunks}
    none = await run(tmp_path, "gamma", vault=vault(claims=False))
    assert "c6" not in {c.id for c in none.chunks}


async def test_scores_add_across_resolved_pages(tmp_path: Path):
    r = await run(tmp_path, "alpha beta")
    by_id = dict(scored(r))
    # c2 is direct for both alpha and beta: idf(alpha) + idf(beta)
    assert by_id["c2"] == pytest.approx(round(idf(2) + idf(3), 9))
    assert (
        r.chunks[0].id == "c3"
    )  # c3: direct for both plus both asserted-link supports; c2 ties on score, support breaks it


async def test_an_unresolved_question_returns_nothing_and_says_so(tmp_path: Path):
    r = await run(tmp_path, "zeta omega")
    assert r.chunks == [] and r.resolution is not None and not r.resolution.any_resolved


async def test_a_hit_for_a_chunk_that_was_deleted_is_skipped(tmp_path: Path):
    store = docs(tmp_path)
    store.delete_document("d")
    r = await VaultRetriever(vault=vault(), docs=store).retrieve("alpha")
    assert r.chunks == []


class StubEmbedder(Embedder):
    """Returns the vector registered for a text, else the zero vector."""

    def __init__(self, table: dict[str, list[float]]):
        self.table = table
        self.calls = 0

    async def embed(self, texts):
        self.calls += len(texts)
        return [self.table.get(t, [0.0, 0.0, 0.0]) for t in texts]


async def test_semantic_resolution_adds_the_two_nearest_pages_only_when_the_lexical_step_is_weak(
    tmp_path: Path,
):
    table = {
        "alpha": [1.0, 0.0, 0.0],
        "beta": [0.0, 1.0, 0.0],
        "gamma": [0.0, 0.0, 1.0],
        "delta": [0.1, 0.9, 0.0],
        "what do you mean about thing": [
            0.0,
            0.6,
            0.8,
        ],  # nearest gamma (0.8), then beta (0.6), then delta (~0.54)
    }
    embedder = StubEmbedder(table)
    vectors = await embed_page_labels(vault(), embedder)
    assert set(vectors) == {"alpha", "beta", "gamma", "delta"}
    r = await run(
        tmp_path,
        "what do you mean about thing",
        embedder=embedder,
        label_vectors=vectors,
        semantic=True,
    )
    assert r.resolution is not None
    assert [(e.node_id, e.weight) for e in r.resolution.entities] == [
        ("gamma", SEMANTIC_WEIGHT),
        ("beta", SEMANTIC_WEIGHT),
    ]
    # a question the lexical step covers fully does not use the embedding step
    calls = embedder.calls
    full = await run(tmp_path, "alpha", embedder=embedder, label_vectors=vectors, semantic=True)
    assert [e.node_id for e in full.resolution.entities] == ["alpha"] and embedder.calls == calls  # type: ignore[union-attr]


async def test_semantic_resolution_needs_an_embedder_and_vectors(tmp_path: Path):
    with pytest.raises(ValueError):
        VaultRetriever(vault=vault(), docs=docs(tmp_path), semantic=True)
