"""The pre-registered question set and the corpus manifest are frozen (constraint 9). Changing either
is a declared amendment: update these hashes in the same commit as an ADR that says why."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

from eval.frozen import (
    APPROVED_GOLD_SHA256,
    HEADER_END,
    MANIFEST_SHA256,
    QUESTIONS_BODY_SHA256,
)

EVAL = Path(__file__).resolve().parents[1]
QUESTIONS = EVAL / "questions.yaml"
MANIFEST = EVAL / "corpus" / "MANIFEST.json"



def test_the_question_set_is_byte_identical_to_v1_below_its_provenance_header():
    raw = QUESTIONS.read_bytes()
    assert raw.startswith(b"# Copied unchanged from Azimlearning/Arcana")
    body = raw[raw.index(HEADER_END) + len(HEADER_END) :]
    assert hashlib.sha256(body).hexdigest() == QUESTIONS_BODY_SHA256


def test_the_corpus_manifest_is_byte_identical_to_v1():
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == MANIFEST_SHA256


def test_the_question_set_has_the_pre_registered_shape():
    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    assert len(questions) == 20 and len({q["id"] for q in questions}) == 20
    assert Counter(q["category"] for q in questions) == {
        "cross_document": 12,
        "single_document": 4,
        "contradiction": 4,
    }
    assert all(q["question"].strip() for q in questions)


def test_the_manifest_lists_sixteen_papers_with_the_fields_the_runner_needs():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(manifest) == 16 and len({m["arxiv_id"] for m in manifest}) == 16
    for entry in manifest:
        assert entry["file"].endswith(".pdf") and entry["arxiv_id"] and entry["title"]


def test_every_gold_file_names_a_real_question_and_real_manifest_papers():
    ids = {q["id"] for q in yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]}
    papers = {m["arxiv_id"] for m in json.loads(MANIFEST.read_text(encoding="utf-8"))}
    files = sorted((EVAL / "gold").glob("q-*.yaml"))
    assert files
    for path in files:
        gold = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert path.stem == gold["question_id"] and gold["question_id"] in ids
        assert gold["status"] in {"smoke", "benchmark", "unanswerable"}
        assert (gold["status"] == "unanswerable") == (not gold["reference_contexts"])
        for passage in gold["reference_contexts"]:
            assert passage["doc_id"] in papers




def test_approved_gold_is_pinned_and_unchanged():
    approved = {}
    for path in sorted((EVAL / "gold").glob("q-*.yaml")):
        if yaml.safe_load(path.read_text(encoding="utf-8")).get("approved_by"):
            approved[path.stem] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert approved == APPROVED_GOLD_SHA256  # same files, same bytes: none unpinned, none edited


def test_every_gold_file_is_approved_including_the_unanswerable_control():
    unapproved = [
        p.stem for p in (EVAL / "gold").glob("q-*.yaml") if not yaml.safe_load(p.read_text(encoding="utf-8")).get("approved_by")
    ]
    assert unapproved == []  # q-single-01 was approved as a "should find nothing" control (ADR D-26)
    assert len(APPROVED_GOLD_SHA256) == 20


# The declared extension (D-39): its own question file and gold, pinned the same way; the frozen files above are untouched.
QUESTIONS_EXT = EVAL / "questions_ext.yaml"
GOLD_EXT = EVAL / "gold_ext"


def test_the_extension_question_file_is_pinned_and_has_its_declared_shape():
    from eval.frozen import EXT_QUESTIONS_BODY_SHA256, questions_body_sha256

    assert questions_body_sha256(QUESTIONS_EXT) == EXT_QUESTIONS_BODY_SHA256
    questions = yaml.safe_load(QUESTIONS_EXT.read_text(encoding="utf-8"))["questions"]
    frozen_ids = {q["id"] for q in yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]}
    assert len(questions) == 19 and len({q["id"] for q in questions}) == 19
    assert not frozen_ids & {q["id"] for q in questions}
    assert Counter(q["category"] for q in questions) == {"single_document": 8, "cross_document": 11}


def test_extension_gold_is_approved_pinned_unchanged_and_cites_manifest_papers():
    from eval.frozen import APPROVED_EXT_GOLD_SHA256

    papers = {m["arxiv_id"] for m in json.loads(MANIFEST.read_text(encoding="utf-8"))}
    ids = {q["id"] for q in yaml.safe_load(QUESTIONS_EXT.read_text(encoding="utf-8"))["questions"]}
    on_disk = {}
    for path in sorted(GOLD_EXT.glob("q-x-*.yaml")):
        gold = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert gold["approved_by"] == "Azim" and gold["question_id"] == path.stem and path.stem in ids
        assert gold["reference_contexts"] and all(c["doc_id"] in papers for c in gold["reference_contexts"])
        on_disk[path.stem] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert on_disk == APPROVED_EXT_GOLD_SHA256 and set(on_disk) == ids


def test_check_frozen_accepts_the_registered_extension_and_refuses_edited_gold(tmp_path):
    from eval.frozen import check_frozen, is_registered_pair

    ids = sorted(yaml.safe_load(QUESTIONS_EXT.read_text(encoding="utf-8"))["questions"][i]["id"] for i in range(19))
    assert check_frozen(QUESTIONS_EXT, MANIFEST, GOLD_EXT, ids) == []
    assert is_registered_pair(QUESTIONS_EXT, GOLD_EXT, EVAL.parent)
    assert not is_registered_pair(QUESTIONS_EXT, EVAL / "gold", EVAL.parent)
    copy = tmp_path / "gold"
    copy.mkdir()
    for path in GOLD_EXT.glob("q-x-*.yaml"):
        (copy / path.name).write_bytes(path.read_bytes())
    target = copy / "q-x-s01.yaml"
    target.write_bytes(target.read_bytes().replace(b"Faithfulness", b"Faithfulnezz", 1))
    problems = check_frozen(QUESTIONS_EXT, MANIFEST, copy, ["q-x-s01"])
    assert any("edited after approval" in p for p in problems)
