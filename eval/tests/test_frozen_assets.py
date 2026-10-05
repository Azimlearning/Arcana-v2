"""The pre-registered question set and the corpus manifest are frozen (constraint 9). Changing either
is a declared amendment: update these hashes in the same commit as an ADR that says why."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

EVAL = Path(__file__).resolve().parents[1]
QUESTIONS = EVAL / "questions.yaml"
MANIFEST = EVAL / "corpus" / "MANIFEST.json"

# SHA-256 of the v1 files this was copied from (Azimlearning/Arcana @ 9a3d67f, pre-registered 9 Jun 2026).
QUESTIONS_BODY_SHA256 = "704e2eb07a88bcb409f4e14c97ddb0c76f6d6b2c6e2d6fdff5742c39125499ea"
MANIFEST_SHA256 = "e00f4270cedf24f2002764399b3ba960c68c933ef7205f8e8fb5d11346462a80"
HEADER_END = b"never an edit.\n\n"  # last line of the provenance header on questions.yaml


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
