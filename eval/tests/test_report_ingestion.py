"""The ingestion cost report attributes ledger rows to papers by position; a wrong guess must stop the report."""

import pytest

from eval.report_ingestion import ReportInvalid, attribute, paper_summary

_ID = 0


def row(purpose: str, tokens_in: int = 500, tokens_out: int = 300, cost: float = 0.001, status: str = "ok") -> dict:
    global _ID
    _ID += 1
    return {"id": _ID, "ts": f"2026-10-06T09:00:{_ID % 60:02d}+00:00", "provider": "x", "model": "m", "purpose": purpose,
            "status": status, "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost}


def paper(arxiv_id: str, chunks: int) -> dict:
    return {"arxiv_id": arxiv_id, "doc_id": "d" + arxiv_id, "chunks": chunks, "nodes": 1, "edges": 1, "extraction_failures": 0}


def ledger() -> list[dict]:
    return [
        row("probe"), row("probe", status="failed"),
        row("extract"), row("extract"),                       # a throwaway measurement before any paper
        row("embed", tokens_in=2), row("embed", tokens_in=9000), row("extract"), row("extract"), row("extract"),   # paper A: 3 chunks
        row("route"), row("research"), row("check"), row("embed", tokens_in=15),                                    # a chat turn between papers
        row("embed", tokens_in=7000), row("embed", tokens_in=6000), row("extract"), row("extract"),                 # paper B: 2 chunks, 2 batches
        row("research"),
    ]


def test_rows_are_attributed_to_their_papers_and_everything_else_is_labelled():
    labelled, blocks = attribute(ledger(), [paper("A", 3), paper("B", 2)])
    by_paper = {b["paper"]["arxiv_id"]: b for b in blocks}
    assert len(by_paper["A"]["embeds"]) == 1 and len(by_paper["A"]["extracts"]) == 3
    assert len(by_paper["B"]["embeds"]) == 2 and len(by_paper["B"]["extracts"]) == 2  # two embedding batches, one paper
    labels = [r["attributed_to"] for r in labelled]
    assert labels.count("A") == 4 and labels.count("B") == 4
    assert "throwaway" in labels[2] and "throwaway" in labels[3]  # extraction rows before the first paper
    assert labels[0].startswith("probe") and "[failed call" in labels[1]
    assert "chat turn" in labels[9] and "embedding outside the ingestion" in labels[12]  # a 15-token query embedding
    assert "chat turn" in labels[-1]


def test_a_block_with_the_wrong_number_of_extraction_rows_stops_the_report():
    with pytest.raises(ReportInvalid, match="expected 4 extraction rows"):
        attribute(ledger(), [paper("A", 4), paper("B", 2)])  # the ledger has 3 for A: never guess


def test_a_ledger_with_no_paper_embedding_is_refused():
    with pytest.raises(ReportInvalid, match="no paper embedding"):
        attribute([row("probe"), row("embed", tokens_in=3)], [paper("A", 1)])


def test_the_per_paper_summary_adds_up():
    _, blocks = attribute(ledger(), [paper("A", 3), paper("B", 2)])
    s = paper_summary(blocks[1])
    assert s["chunks"] == 2 and s["embedding_calls"] == 2 and s["embedding_tokens"] == 13000
    assert s["extraction_calls"] == 2 and s["extraction_tokens_out"] == 600
    assert s["total_cost_usd"] == pytest.approx(0.004) and s["cost_per_chunk_usd"] == pytest.approx(0.002)
    assert s["output_tokens"]["max"] == 300 and s["output_tokens"]["at_limit"] == 0
