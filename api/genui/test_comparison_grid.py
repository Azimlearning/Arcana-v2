"""ComparisonGrid: every tampered field is rejected with its path, and the Composer only offers a grounded grid."""

import copy

import pytest

from api.agents.compose import compose
from api.agents.framework import AgentResult
from api.agents.test_agents import GRAPH, QUESTION, make_ctx
from api.core.errors import ValidationFailed
from api.genui.builders import comparison_grid
from api.genui.catalog import alignment_grid
from api.genui.evidence import excerpt_containing
from api.genui.generated import ComparisonGrid
from api.genui.validate import validate_block
from api.stores.doc_store import Chunk, Document

LABELS = {"dense": "Dense Retrieval", "bm25": "BM25"}


@pytest.fixture
def world(ingested):
    """(deps, d1, d2, cells): the ingested paper plus a second one, and a quote per (paper, entity)."""
    deps, result = ingested
    d1 = result.doc_id
    deps.docs.put_document(Document("d2", "Second Paper", "second.pdf", "ready", 1, None, "t"))
    deps.docs.put_chunks(
        [
            Chunk("d2_c1", "d2", 0, 2, "In this second paper, Dense Retrieval underpins the baseline pipeline."),
            Chunk("d2_c2", "d2", 1, 3, "The second paper uses BM25 as the sparse arm of its pipeline."),
        ]
    )
    cells = {}
    for doc_id in (d1, "d2"):
        for dim, label in LABELS.items():
            for chunk in deps.docs.chunks_for_document(doc_id):
                quote = excerpt_containing(chunk.text, [label])
                if quote:
                    document = deps.docs.get_document(doc_id)
                    assert document is not None
                    cells[(doc_id, dim)] = {
                        "doc_id": doc_id,
                        "dimension_id": dim,
                        "chunk_id": chunk.id,
                        "page": chunk.page,
                        "quote": quote,
                        "doc_title": document.title,
                    }
                    break
    assert len(cells) == 4, "the fixtures must name both entities in both papers"
    return deps, d1, cells


def graph_payload(deps, d1, cells):
    docs = [{"doc_id": d, "title": deps.docs.get_document(d).title} for d in (d1, "d2")]
    dims = [{"id": k, "label": v} for k, v in LABELS.items()]
    return {
        "edges": [],
        "labels": {},
        "alignment": {"documents": docs, "dimensions": dims, "cells": list(cells.values())},
    }


@pytest.fixture
def base(world):
    deps, d1, cells = world
    citations, rows = [], []
    for doc_id in (d1, "d2"):
        row_cells = []
        for dim in LABELS:
            cell = cells[(doc_id, dim)]
            cid = f"c{len(citations) + 1}"
            citations.append(
                {
                    "id": cid,
                    "chunkId": cell["chunk_id"],
                    "docId": doc_id,
                    "docTitle": cell["doc_title"],
                    "page": cell["page"],
                    "quote": cell["quote"],
                }
            )
            row_cells.append({"dimensionId": dim, "citationId": cid})
        rows.append({"docId": doc_id, "docTitle": deps.docs.get_document(doc_id).title, "cells": row_cells})
    data = {"dimensions": [{"id": k, "label": v} for k, v in LABELS.items()], "rows": rows, "citations": citations}
    return deps.docs, comparison_grid("g", "ready", data=data)


def fails(raw, docs) -> list[str]:
    with pytest.raises(ValidationFailed) as exc:
        validate_block(raw, docs)
    return [i.path for i in exc.value.issues]


def test_a_grounded_grid_passes(base):
    docs, raw = base
    block = validate_block(raw, docs)
    assert isinstance(block, ComparisonGrid) and len(block.data.rows) == 2 and len(block.data.citations) == 4


def test_a_cell_citing_another_documents_chunk_is_rejected(base):
    docs, raw = base
    row = raw["data"]["rows"][0]
    row["cells"][0]["citationId"] = "c3"  # c3 is the second paper's quote
    assert "data.rows.0.cells.0.citationId" in fails(raw, docs)


def test_a_quote_without_the_dimension_label_is_rejected(base):
    docs, raw = base
    raw["data"]["dimensions"][1]["label"] = "Louvain communities"
    paths = fails(raw, docs)
    assert "data.rows.0.cells.1.citationId" in paths and "data.rows.1.cells.1.citationId" in paths


def test_a_dimension_supported_in_only_one_row_is_rejected(base):
    docs, raw = base
    raw["data"]["rows"][1]["cells"].pop()  # the second paper no longer has a BM25 cell; its citation is now orphaned
    paths = fails(raw, docs)
    assert "data.dimensions.1" in paths and "data.citations.3" in paths


def test_two_columns_with_one_label_are_rejected(base):
    docs, raw = base
    raw["data"]["dimensions"][1]["label"] = "dense retrieval"  # the same label as the first column, in other case
    assert "data.dimensions.1.label" in fails(raw, docs)


def test_a_row_with_no_cells_is_rejected(base):
    docs, raw = base
    raw["data"]["rows"][1]["cells"] = []
    assert "data.rows.1.cells" in fails(raw, docs)


def test_a_row_for_an_unknown_document_or_with_the_wrong_title_is_rejected(base):
    docs, raw = base
    ghost = copy.deepcopy(raw)
    ghost["data"]["rows"][1]["docId"] = "ghost"
    assert "data.rows.1.docId" in fails(ghost, docs)
    retitled = copy.deepcopy(raw)
    retitled["data"]["rows"][1]["docTitle"] = "Another Title"
    assert fails(retitled, docs) == ["data.rows.1.docTitle"]


def test_a_cell_for_an_unknown_dimension_or_citation_is_rejected(base):
    docs, raw = base
    unknown_dim = copy.deepcopy(raw)
    unknown_dim["data"]["rows"][0]["cells"][0]["dimensionId"] = "nope"
    assert "data.rows.0.cells.0.dimensionId" in fails(unknown_dim, docs)
    unknown_cite = copy.deepcopy(raw)
    unknown_cite["data"]["rows"][0]["cells"][0]["citationId"] = "c9"
    assert "data.rows.0.cells.0.citationId" in fails(unknown_cite, docs)


def test_two_cells_for_one_dimension_in_a_row_are_rejected(base):
    docs, raw = base
    row = raw["data"]["rows"][0]
    row["cells"].append(dict(row["cells"][0]))
    assert "data.rows.0.cells.2.dimensionId" in fails(raw, docs)


def test_more_rows_or_dimensions_than_the_caps_are_rejected(base):
    docs, raw = base
    many_rows = copy.deepcopy(raw)
    many_rows["data"]["rows"] = many_rows["data"]["rows"] * 4  # 8 rows
    assert "data.rows" in fails(many_rows, docs)
    many_dims = copy.deepcopy(raw)
    many_dims["data"]["dimensions"] += [{"id": f"x{i}", "label": f"Entity {i}"} for i in range(8)]
    assert "data.dimensions" in fails(many_dims, docs)


def test_a_ready_grid_needs_two_documents_and_two_entities_and_placeholders_carry_nothing(base):
    docs, raw = base
    assert "data" in fails(comparison_grid("g", "ready"), docs)
    assert validate_block(comparison_grid("g", "loading"), docs).meta.status == "loading"
    assert fails(comparison_grid("g", "empty", data=raw["data"]), docs) == ["data"]


# ── what the Composer may offer: a pure function of the Graph agent's alignment ──


def test_the_alignment_is_offered_only_with_two_documents_and_two_entities(world):
    deps, d1, cells = world
    documents, dimensions, offered = alignment_grid(graph_payload(deps, d1, cells))
    assert len(documents) == 2 and len(dimensions) == 2 and len(offered) == 4

    one_entity = {k: v for k, v in cells.items() if k[1] == "dense"}
    assert alignment_grid(graph_payload(deps, d1, one_entity)) == ([], [], [])
    one_paper = {k: v for k, v in cells.items() if k[0] == d1}
    assert alignment_grid(graph_payload(deps, d1, one_paper)) == ([], [], [])
    assert alignment_grid(None) == ([], [], []) and alignment_grid({}) == ([], [], [])


def test_a_cell_whose_quote_lacks_its_label_or_title_is_left_out_and_can_sink_the_grid(world):
    deps, d1, cells = world
    broken = dict(cells)
    broken[("d2", "bm25")] = {**cells[("d2", "bm25")], "quote": "A long enough sentence that names nothing."}
    # BM25 is then evidenced in one paper only, so it is dropped, leaving one entity: no grid.
    assert alignment_grid(graph_payload(deps, d1, broken)) == ([], [], [])
    retitled = dict(cells)
    retitled[("d2", "bm25")] = {**cells[("d2", "bm25")], "doc_title": "Not the title"}
    assert alignment_grid(graph_payload(deps, d1, retitled)) == ([], [], [])


async def test_the_composer_offers_a_valid_grid_for_a_grounded_alignment_and_refuses_otherwise(world, tmp_path):
    deps, d1, cells = world
    ctx = make_ctx(deps, tmp_path)
    await GRAPH.ainvoke({"question": QUESTION}, context=ctx)  # a real turn, so Research and the checker have run
    ctx.results["graph"] = AgentResult("graph", "ok", graph_payload(deps, d1, cells))
    composition = compose(ctx)
    grid = next(b for b in composition.blocks if b.type == "ComparisonGrid")
    assert isinstance(grid, ComparisonGrid) and grid.id == f"{ctx.block_id}-comparison-grid"
    assert [r.docId for r in grid.data.rows] == [d1, "d2"] and len(grid.data.dimensions) == 2
    record = next(r for r in composition.records if r.component == "ComparisonGrid")
    assert record.outcome == "admitted" and record.block_id == grid.id
    assert composition.primary.type == "CitedSummary"  # the answer still comes first

    ctx.results["graph"] = AgentResult(
        "graph", "ok", graph_payload(deps, d1, {k: v for k, v in cells.items() if k[1] == "dense"})
    )
    refused = next(r for r in compose(ctx).records if r.component == "ComparisonGrid")
    assert refused.outcome == "refused" and refused.reasons == ("no_shared_entities",)
