import json

import pytest

from api.core.errors import IngestFailed
from api.ingestion.extract import (
    _parse_json,  # pyright: ignore[reportPrivateUsage]
    build_result,
    extract_chunk,
    slug,
)
from api.ingestion.fakes import fake_extraction_responder
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService
from api.stores.doc_store import Chunk

CHUNK = Chunk(id="d_c_1", doc_id="d", ordinal=0, page=1, text="text")


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("GraphRAG", "graph_rag"),
        ("graph rag", "graph_rag"),
        ("Knowledge Graphs", "knowledge_graph"),
        ("ontologies", "ontology"),
        ("Bias", "bias"),
        ("analysis", "analysis"),
        ("  Reciprocal-Rank  Fusion ", "reciprocal_rank_fusion"),
        ("???", "unknown"),
    ],
)
def test_slug_canonicalises(label: str, expected: str):
    assert slug(label) == expected


def test_parse_tolerates_fences_and_surrounding_prose():
    assert _parse_json('```json\n{"entities": []}\n```') == {"entities": []}
    assert _parse_json('Here you go: {"entities": []} Hope that helps!') == {"entities": []}


@pytest.mark.parametrize("raw", ["no json at all", "{broken", "[1, 2]", ""])
def test_parse_rejects_malformed_replies(raw: str):
    with pytest.raises(IngestFailed):
        _parse_json(raw)


def test_build_result_resolves_relations_and_records_provenance():
    parsed = {
        "entities": [
            {"label": "Dense Retrieval", "type": "Method"},
            {"label": "BM25", "type": "method"},
            {"label": "dense retrieval", "type": "x"},  # duplicate of the first
        ],
        "relationships": [
            {"src": "Dense Retrieval", "dst": "BM25", "type": "Is Fused With"},
            {"src": "BM25", "dst": "Ghost", "type": "uses"},  # unlisted entity: dropped
            {"src": "BM25", "dst": "BM25", "type": "uses"},  # self loop: dropped
            {"src": "BM25", "dst": "Dense Retrieval", "type": ""},  # no type: dropped
        ],
    }
    result = build_result(parsed, CHUNK)
    assert sorted(n.id for n in result.nodes) == ["bm25", "dense_retrieval"]
    first = next(n for n in result.nodes if n.id == "dense_retrieval")
    assert first.label == "Dense Retrieval" and first.type == "method" and first.doc_ids == ("d",)
    assert [(e.src, e.dst, e.relation, e.chunk_id, e.doc_id) for e in result.edges] == [
        ("dense_retrieval", "bm25", "is fused with", "d_c_1", "d")
    ]


def test_build_result_rejects_the_wrong_shape():
    with pytest.raises(IngestFailed):
        build_result({"entities": "nope"}, CHUNK)


def test_build_result_bounds_runaway_output():
    parsed = {"entities": [{"label": f"Entity {i} Name", "type": "t"} for i in range(500)]}
    assert len(build_result(parsed, CHUNK).nodes) == 30


def test_fake_responder_reads_the_passage_and_links_terms():
    from api.ingestion.extract import build_prompt
    from api.llm.types import LLMRequest

    reply = fake_extraction_responder(
        LLMRequest(prompt=build_prompt("Dense Retrieval and BM25 meet Reciprocal Rank Fusion."), purpose="extract")
    )
    data = json.loads(reply)
    labels = [e["label"] for e in data["entities"]]
    assert labels[0] == "Dense Retrieval" and "BM25" in labels
    assert data["relationships"][0]["src"] == labels[0]


async def test_extract_chunk_uses_the_light_tier_and_the_extract_purpose(tmp_path):
    from sqlalchemy import create_engine

    from api.llm.ledger import SpendLedger

    provider = FakeProvider(fake_extraction_responder)
    ledger = SpendLedger(create_engine(f"sqlite:///{tmp_path / 'l.db'}"), None)
    chunk = Chunk("d_c_9", "d", 0, 1, "Dense Retrieval meets BM25.")
    await extract_chunk(chunk, LLMService(provider, None, ledger))
    assert provider.calls[0].tier == "light" and provider.calls[0].purpose == "extract"
    assert ledger.rows()[0]["purpose"] == "extract"


def test_every_extracted_node_records_the_chunk_it_came_from():
    parsed = {"entities": [{"label": "BM25", "type": "method"}, {"label": "Dense Retrieval"}]}
    result = build_result(parsed, CHUNK)
    assert all(n.chunk_ids == ("d_c_1",) for n in result.nodes)


def test_a_label_with_no_letters_or_digits_never_becomes_a_node():
    parsed = {"entities": [{"label": "???"}, {"label": "BM25"}], "relationships": [{"src": "???", "dst": "BM25", "type": "x"}]}
    result = build_result(parsed, CHUNK)
    assert [n.id for n in result.nodes] == ["bm25"] and result.edges == []
