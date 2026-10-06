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


# Gold approved by Azim on 2026-10-06 (benchmark gold, written before any arm was run). A change to any of
# these files is a declared amendment: update the hash in the same commit as an ADR that says why. A file
# that becomes approved must be pinned here (test below), so approval cannot happen without being frozen.
APPROVED_GOLD_SHA256 = {
    "q-contra-01": "6b948862ed26e55ee395c307782e41d017dae135354c7957869613723bf1c91a",
    "q-contra-02": "726b1c81fbe3f654172f2f968b9f845fe3f14df7273402bb42e07a694e9d5b4b",
    "q-contra-03": "eb576a76dd5f25c464ed89d4dd0cabd1825544474fb71b8cb5b8116be1f2c7f8",
    "q-contra-04": "54e051968a3802084cadddb2ad7fe04e637552ea3c52df33e904b2fef39d20f5",
    "q-cross-01": "52425dbffdd176b92f92940444f5e2f1758d99f7040f6bdb31786a95b6c2cf6c",
    "q-cross-02": "1a4ebb30e3a5bed0ed99bd69b3e6e13ef1da4b6a8017421607be635aca0bfd01",
    "q-cross-03": "19d91ef1c942588969b2aa9ff8a0c7f68bd6b955aced9210702081109ba9eae8",
    "q-cross-04": "92cf9222b5f524d11c794a8ba83f64ab34282cdcf7c11b6027cbf14d1d5e40af",
    "q-cross-05": "393943eb125b71a5561d7cd860ec80a1a2db15019523c85a38fa8abc451545af",
    "q-cross-06": "a38a30296a50928c4320aeec05ed1db53817c01428a9c64cc6ca94aa8cf39d62",
    "q-cross-07": "79fcb99eef04760cb454593f70c7561690cd432076544866785077df7d1a01ba",
    "q-cross-08": "2fd3ca4928f38f608685d82dbeb485f3d85ac0972aeebcc90b78956be560366e",
    "q-cross-09": "1f742209c9b08f085fc55207ee9db3ad3345fd73d163cc7d74fac9db300c4e27",
    "q-cross-10": "235804cbd88c14c69dda9775f76f4b6fb43a64d99ab403a2a7a6744fa9164db6",
    "q-cross-11": "e0a63d41de0d32b0de5424c6eb8513d1a708b882ce1431b8770562291d077099",
    "q-cross-12": "a67d528a5108e07f858ab2cba845b76ecf444092beb222820472e2a460ea10f7",
    "q-single-02": "2ecf53550aa626a19e79792ad8d5388fba4819afb535bcfc66c8dde3ff4299c5",
    "q-single-03": "314ec9ea53fd833d809a7246846b4cd63c227f6425ca619e0040cadd8f224339",
    "q-single-04": "3a4a3a57e5770407c4fd5de7729e0ddd3952113ddceaf5753e9b508cd361e37a",
}


def test_approved_gold_is_pinned_and_unchanged():
    approved = {}
    for path in sorted((EVAL / "gold").glob("q-*.yaml")):
        if yaml.safe_load(path.read_text(encoding="utf-8")).get("approved_by"):
            approved[path.stem] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert approved == APPROVED_GOLD_SHA256  # same files, same bytes: none unpinned, none edited


def test_the_one_unapproved_file_is_the_unanswerable_control_awaiting_its_amendment():
    unapproved = [
        p.stem for p in (EVAL / "gold").glob("q-*.yaml") if not yaml.safe_load(p.read_text(encoding="utf-8")).get("approved_by")
    ]
    assert unapproved == ["q-single-01"]  # ADR D-21: amendment pending
