"""ConceptMap: tampered steps are rejected with their path, and the Composer only offers a fully grounded path."""

import copy

import pytest

from api.agents.compose import compose
from api.agents.framework import AgentResult
from api.agents.test_agents import GRAPH, QUESTION, make_ctx
from api.core.errors import ValidationFailed
from api.genui.builders import concept_map
from api.genui.catalog import cap, concept_path
from api.genui.evidence import excerpt_containing
from api.genui.generated import ConceptMap
from api.genui.validate import validate_block
from api.stores.doc_store import Chunk, Document

TEXTS = [
    "Alpha Method builds on Beta Index for fast lookup.",
    "Beta Index is compared with Gamma Cache in experiments.",
    "Gamma Cache feeds the Delta Store in the pipeline.",
]
PATH = ["Alpha Method", "Beta Index", "Gamma Cache", "Delta Store"]
RELATIONS = ["builds_on", "compared_with", "feeds"]


@pytest.fixture
def world(ingested):
    deps, _ = ingested
    deps.docs.put_document(Document("dp", "Path Paper", "path.pdf", "ready", 1, None, "t"))
    deps.docs.put_chunks([Chunk(f"dp_c{i}", "dp", i, i + 1, t) for i, t in enumerate(TEXTS)])
    edges = []
    for i, relation in enumerate(RELATIONS):
        quote = excerpt_containing(TEXTS[i], [PATH[i], PATH[i + 1]])
        assert quote
        edges.append(
            {
                "src": f"n{i}",
                "dst": f"n{i + 1}",
                "relation": relation,
                "chunk_id": f"dp_c{i}",
                "doc_id": "dp",
                "quote": quote,
                "page": i + 1,
                "doc_title": "Path Paper",
            }
        )
    payload = {
        "mode": "path",
        "entities": ["n0", "n3"],
        "edges": edges,
        "labels": {f"n{i}": name for i, name in enumerate(PATH)},
    }
    return deps, payload


@pytest.fixture
def base(world):
    deps, payload = world
    steps, reason = concept_path(payload)
    assert reason is None
    citations = [
        {
            "id": f"c{i + 1}",
            "chunkId": s["chunk_id"],
            "docId": s["doc_id"],
            "docTitle": s["doc_title"],
            "page": s["page"],
            "quote": s["quote"],
        }
        for i, s in enumerate(steps)
    ]
    raw_steps = [
        {
            "source": s["source"],
            "target": s["target"],
            "relation": s["relation"],
            "reversed": s["reversed"],
            "citationId": f"c{i + 1}",
        }
        for i, s in enumerate(steps)
    ]
    return deps.docs, concept_map("m", "ready", data={"steps": raw_steps, "citations": citations})


def fails(raw, docs) -> list[str]:
    with pytest.raises(ValidationFailed) as exc:
        validate_block(raw, docs)
    return [i.path for i in exc.value.issues]


# ── the validator ─────────────────────────────────────────────────────────────


def test_a_grounded_three_hop_path_passes(base):
    docs, raw = base
    block = validate_block(raw, docs)
    assert isinstance(block, ConceptMap) and [s.target for s in block.data.steps] == PATH[1:]


def test_non_contiguous_steps_are_rejected(base):
    docs, raw = base
    raw["data"]["steps"][1]["source"] = "Somewhere Else"
    assert "data.steps.1.source" in fails(raw, docs)


def test_a_repeated_concept_is_rejected(base):
    docs, raw = base
    raw["data"]["steps"][2]["target"] = "Alpha Method"
    assert "data.steps.2.target" in fails(raw, docs)


def test_a_quote_without_a_label_is_rejected(base):
    docs, raw = base
    raw["data"]["steps"][1]["target"] = "Louvain communities"  # the quote never says this
    assert "data.steps.1.citationId" in fails(raw, docs)


def test_a_step_citing_a_missing_chunk_is_rejected(base):
    docs, raw = base
    raw["data"]["citations"][1]["chunkId"] = "no-such-chunk"
    assert fails(raw, docs) == ["data.citations.1.chunkId"]


def test_a_step_citing_nothing_and_an_orphan_citation_are_rejected(base):
    docs, raw = base
    ghost = copy.deepcopy(raw)
    ghost["data"]["steps"][0]["citationId"] = "c9"
    paths = fails(ghost, docs)
    assert "data.steps.0.citationId" in paths and "data.citations.0" in paths
    extra = copy.deepcopy(raw)
    extra["data"]["citations"].append(dict(extra["data"]["citations"][0], id="c4"))
    assert fails(extra, docs) == ["data.citations.3"]


def test_too_few_or_too_many_steps_are_rejected(base):
    docs, raw = base
    short = copy.deepcopy(raw)
    short["data"]["steps"] = short["data"]["steps"][:1]
    assert "data.steps" in fails(short, docs)
    long = copy.deepcopy(raw)
    long["data"]["steps"] = long["data"]["steps"] * 3  # 9 steps
    assert "data.steps" in fails(long, docs)


def test_an_over_long_relation_or_label_is_rejected_but_a_flipped_reversed_flag_is_only_a_claim(base):
    docs, raw = base
    long_relation = copy.deepcopy(raw)
    long_relation["data"]["steps"][0]["relation"] = "x" * 81
    assert "data.steps.0.relation" in fails(long_relation, docs)
    long_label = copy.deepcopy(raw)
    long_label["data"]["steps"][0]["source"] = "Alpha Method " + "y" * 120
    assert "data.steps.0.source" in fails(long_label, docs)
    flipped = copy.deepcopy(raw)
    flipped["data"]["steps"][1]["reversed"] = True  # direction is the Composer's claim; the quote shows co-mention
    assert validate_block(flipped, docs).meta.status == "ready"


def test_placeholders_carry_nothing(base):
    docs, raw = base
    assert validate_block(concept_map("m", "loading"), docs).meta.status == "loading"
    assert fails(concept_map("m", "empty", data=raw["data"]), docs) == ["data"]


# ── what the Composer may offer: a pure function of the Graph agent's path ────


def test_a_three_hop_path_becomes_steps_in_path_order(world):
    _, payload = world
    steps, reason = concept_path(payload)
    assert reason is None
    assert [(s["source"], s["target"], s["relation"], s["reversed"]) for s in steps] == [
        ("Alpha Method", "Beta Index", "builds on", False),
        ("Beta Index", "Gamma Cache", "compared with", False),
        ("Gamma Cache", "Delta Store", "feeds", False),
    ]


def test_a_hop_stored_against_the_path_is_marked_reversed_not_flipped(world):
    _, payload = world
    flipped = copy.deepcopy(payload)
    flipped["edges"][1]["src"], flipped["edges"][1]["dst"] = "n2", "n1"  # the document says Gamma Cache ... Beta Index
    steps, reason = concept_path(flipped)
    assert reason is None and [s["reversed"] for s in steps] == [False, True, False]
    assert steps[1]["source"] == "Beta Index" and steps[1]["target"] == "Gamma Cache"  # still in path order


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda p: p.update(edges=p["edges"][:1]), "single_hop"),
        (lambda p: p["edges"][1].update(quote=None), "ungrounded_hop"),  # an ungrounded middle hop breaks the path
        (lambda p: p["edges"][1].update(quote="A long enough sentence that names neither concept."), "ungrounded_hop"),
        (lambda p: p.update(mode="neighborhood"), "not_a_path"),
        (lambda p: p.update(edges=[]), "not_a_path"),
        (lambda p: p["edges"][1].update(src="n9", dst="n8"), "broken_path"),
        (lambda p: p["labels"].update(n3="Alpha Method"), "ungrounded_hop"),  # its quote does not name that label
        (lambda p: p.update(edges=p["edges"] * 3), "path_too_long"),
    ],
)
def test_a_path_that_cannot_be_drawn_says_why(world, change, reason):
    _, payload = world
    broken = copy.deepcopy(payload)
    change(broken)
    assert concept_path(broken) == ([], reason)
    assert concept_path(None) == ([], "no_graph_result")
    assert cap("ConceptMap", "steps") == 6


def test_a_path_that_ends_at_the_wrong_entity_is_refused(world):
    _, payload = world
    wrong = copy.deepcopy(payload)
    wrong["entities"] = ["n0", "n2"]  # the walk reaches n3, not the second entity
    assert concept_path(wrong) == ([], "broken_path")


def test_two_hops_in_one_sentence_share_one_citation(world):
    _, payload = world
    shared = copy.deepcopy(payload)
    sentence = "Alpha Method builds on Beta Index, which is compared with Gamma Cache."
    for edge in shared["edges"][:2]:
        edge["quote"], edge["chunk_id"] = sentence, "dp_c0"
    steps, reason = concept_path(shared)
    assert reason is None and steps[0]["quote"] == steps[1]["quote"]


def test_a_repeated_concept_in_the_path_is_refused(world):
    _, payload = world
    looped = copy.deepcopy(payload)
    looped["labels"]["n2"] = "alpha  method"  # the same concept as the start, in other case and spacing
    looped["edges"][1]["quote"] = "Beta Index is compared with alpha method in experiments."
    looped["edges"][2]["quote"] = "alpha  method feeds the Delta Store in the pipeline."
    assert concept_path(looped) == ([], "repeated_concept")


async def test_the_composer_offers_a_valid_map_for_a_grounded_path_and_refuses_a_single_hop(world, tmp_path):
    deps, payload = world
    ctx = make_ctx(deps, tmp_path)
    await GRAPH.ainvoke({"question": QUESTION}, context=ctx)  # a real turn, so Research and the checker have run
    ctx.results["graph"] = AgentResult("graph", "ok", payload)
    composition = compose(ctx)
    block = next(b for b in composition.blocks if b.type == "ConceptMap")
    assert isinstance(block, ConceptMap) and block.id == f"{ctx.block_id}-concept-map"
    assert len(block.data.steps) == 3 and len(block.data.citations) == 3
    assert next(r for r in composition.records if r.component == "ConceptMap").outcome == "admitted"

    one_hop = {**payload, "edges": payload["edges"][:1], "entities": ["n0", "n1"]}
    ctx.results["graph"] = AgentResult("graph", "ok", one_hop)
    refused = next(r for r in compose(ctx).records if r.component == "ConceptMap")
    assert refused.outcome == "refused" and refused.reasons == ("single_hop",)
