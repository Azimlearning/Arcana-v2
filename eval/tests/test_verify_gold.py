"""The gold verifier on the fixture PDF: a passage must be verbatim on its page and reachable by a chunk."""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from eval.verify_gold import main, verify

FIXTURE = Path(__file__).resolve().parents[2] / "api" / "tests" / "fixtures" / "hybrid_retrieval.pdf"
DOC = "0000.00000v1"
# A real passage of page 2 of the fixture.
GOOD = (
    "The three rankings are merged with Reciprocal Rank Fusion. A passage at rank r in a list "
    "contributes one over the sum of a constant k and r, and contributions add across lists."
)


@pytest.fixture
def setup(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    shutil.copy(FIXTURE, corpus / "paper.pdf")
    manifest = [{"arxiv_id": DOC, "title": "T", "file": "paper.pdf"}]
    gold = tmp_path / "gold"
    gold.mkdir()

    def put(qid: str, passages: list[dict], status: str = "benchmark") -> None:
        body = {"question_id": qid, "status": status, "reference_contexts": passages}
        (gold / f"{qid}.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")

    return corpus, manifest, gold, put


def test_a_verbatim_reachable_passage_has_no_problems(setup):
    corpus, manifest, gold, put = setup
    put("q-1", [{"doc_id": DOC, "page": 2, "text": GOOD}])
    assert verify(gold, manifest, corpus, None) == []


def test_whitespace_differences_do_not_matter(setup):
    corpus, manifest, gold, put = setup
    put("q-1", [{"doc_id": DOC, "page": 2, "text": GOOD.replace(" ", "  \n ")}])
    assert verify(gold, manifest, corpus, None) == []


def test_an_altered_passage_is_not_verbatim(setup):
    corpus, manifest, gold, put = setup
    put("q-1", [{"doc_id": DOC, "page": 2, "text": GOOD.replace("merged", "combined")}])
    (problem,) = verify(gold, manifest, corpus, None)
    assert "not verbatim" in problem and "not in the paper" in problem


def test_a_wrong_page_says_which_page_it_is_on(setup):
    corpus, manifest, gold, put = setup
    put("q-1", [{"doc_id": DOC, "page": 1, "text": GOOD}])
    (problem,) = verify(gold, manifest, corpus, None)
    assert "found on page [2]" in problem


def test_an_unknown_document_is_reported(setup):
    corpus, manifest, gold, put = setup
    put("q-1", [{"doc_id": "9999.99999v9", "page": 1, "text": GOOD}])
    assert "not in the manifest" in verify(gold, manifest, corpus, None)[0]


def test_the_status_filter_skips_other_files(setup):
    corpus, manifest, gold, put = setup
    put("q-smoke", [{"doc_id": DOC, "page": 1, "text": "nonsense that is nowhere"}], status="smoke")
    put("q-real", [{"doc_id": DOC, "page": 2, "text": GOOD}])
    assert verify(gold, manifest, corpus, "benchmark") == []
    assert len(verify(gold, manifest, corpus, "smoke")) == 1


def test_main_exits_nonzero_on_a_problem(setup, capsys: pytest.CaptureFixture[str], tmp_path: Path):
    corpus, manifest, gold, put = setup
    put("q-1", [{"doc_id": DOC, "page": 1, "text": "not in the paper at all"}])
    manifest_path = tmp_path / "m.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    code = main(["--manifest", str(manifest_path), "--corpus-dir", str(corpus), "--gold-dir", str(gold)])
    assert code == 1 and "FAIL" in capsys.readouterr().out
