"""The pre-registered, frozen assets of the benchmark (constraint 9), as one importable place.

Both pytest (eval/tests/test_frozen_assets.py) and the paid runner (eval/run_ablation.py) check against
these, so the freeze cannot be skipped by running the runner directly. Changing any value is a declared
amendment: update it in the same commit as an ADR that says why, and never pool results across the change.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from api.retrieval.protocol import protocol_stamp

# SHA-256 of the v1 files these were copied from (Azimlearning/Arcana @ 9a3d67f, pre-registered 9 Jun 2026).
QUESTIONS_BODY_SHA256 = "704e2eb07a88bcb409f4e14c97ddb0c76f6d6b2c6e2d6fdff5742c39125499ea"
MANIFEST_SHA256 = "e00f4270cedf24f2002764399b3ba960c68c933ef7205f8e8fb5d11346462a80"
HEADER_END = b"never an edit.\n\n"  # last line of the provenance header on questions.yaml

# The declared extension to the question set (D-39, approved by Azim 2026-10-15): 19 new questions in their own file and gold directory, so
# every frozen file above stays byte-identical. The body hash is taken after the marker line, with line endings normalised.
EXT_HEADER_END = b"# HEADER_END\n"
EXT_QUESTIONS_BODY_SHA256 = "0b088d4b6a2cad75df6361cddb97a9a0cd7d8b6a295d13b1be501222056513a9"
APPROVED_EXT_GOLD_SHA256 = {
    "q-x-c01": "4a341f2b18660399849d9d11818370d83f5156814f367e34fe272aa1946fbc3a",
    "q-x-c02": "3081db72e812f33039e742411499bb782df04dd7ec3d4505867cda9c5d18561d",
    "q-x-c03": "142e35aff8e96b412c8e8b2ca654bfd15fd0074a763440101a44a7bde3ada0cc",
    "q-x-c04": "92a00ef752b906d5471a098afe0383853a226b2bd0e51ded4243067e78ad5199",
    "q-x-c05": "a70fe1d945da0f69f270a1bb43748a4074ade7b251223c5b8258ad5e76840b90",
    "q-x-c06": "1a79839d41e59fd2bbcc621512de543da32ecee7bf95b743709f15c74af580a2",
    "q-x-c07": "bf23e658152894e41bed538e21266004ac57fd57357b1046e65f8c5e3706807b",
    "q-x-c08": "88e0256c5ca16816078c341525cb9988d8fba123e0d461101be96896cfb501a9",
    "q-x-c09": "37f4f47a1d244e2097871bf99c95e308d179ebef29e740bd0b367d4c840981bc",
    "q-x-c10": "c58835cf4c746970838aab647c32fedff6165796e6175b514d1d7fc130466e6c",
    "q-x-c11": "8c62f2bc9bf4e8d9c0109fa6bed4e4b8ab39edaea11fabad6a07e10cc18886a3",
    "q-x-s01": "5f76cb787ce644e2d3a32f08fa3441e2d7b2d30373c6134e09d64b89093cc110",
    "q-x-s02": "a3f478d98a839fb15dbd3cae8b905aa3ce7e28c401a43962b849bfcec3fd0944",
    "q-x-s03": "40ffcd2178fe0487d1db6f0d94e9b339021a8682d23c3f18bd22973e24131ca8",
    "q-x-s04": "d49c40f64e5b1047d96ebbdb7852dffea2669bd52852ca29e449920c1bc899d9",
    "q-x-s05": "fc600a5a96e3ccf2bca322995d0ed60c5aa2eaaff9892e0158bf896745f3489e",
    "q-x-s06": "4bd27f573245cffa5794b469941b9d95c06877093a3511443380921be1de6952",
    "q-x-s07": "cc53ec5cae54adff7f1d44b9dd2421f9cc521bb8d9388aa36e5edb775235e90c",
    "q-x-s08": "6bc10d702f7a26d8d764a8fe209e1b481ef39092e2576e574d389cc89473e2ed",
}

# SHA-256 of the whole retrieval protocol stamp (api/retrieval/protocol.py), canonical JSON. Changing any
# frozen retrieval constant changes this; it then needs a GRAPH_SCORING_VERSION bump and an ADR (D-20).
PROTOCOL_STAMP_SHA256 = "16afb1a3b478e3437012526163babede56ea28c2b5b2ebf09283bead1094a3d4"

# Gold approved by Azim on 2026-10-06 (benchmark gold, written before any arm was run).
APPROVED_GOLD_SHA256 = {
    "q-single-01": "6701bd090d329a94b5e9ab3e088decdb4aaeb01227e345e1b0b257d4cdc35ceb",
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


def questions_body_sha256(path: Path) -> str:
    raw = path.read_bytes()
    if HEADER_END in raw:
        return hashlib.sha256(raw[raw.index(HEADER_END) + len(HEADER_END) :]).hexdigest()
    raw = raw.replace(b"\r\n", b"\n")  # the extension file: line endings normalised before the hash
    return hashlib.sha256(raw[raw.index(EXT_HEADER_END) + len(EXT_HEADER_END) :]).hexdigest()


def is_registered_pair(questions_path: Path, gold_dir: Path, root: Path) -> bool:
    """True for the frozen question set with the frozen gold, or the declared extension with its own gold (D-39)."""
    pair = (questions_path.resolve(), gold_dir.resolve())
    return pair in {
        ((root / "eval" / "questions.yaml").resolve(), (root / "eval" / "gold").resolve()),
        ((root / "eval" / "questions_ext.yaml").resolve(), (root / "eval" / "gold_ext").resolve()),
    }


def stamp_sha256() -> str:
    return hashlib.sha256(json.dumps(protocol_stamp(), sort_keys=True).encode()).hexdigest()


def check_frozen(questions_path: Path, manifest_path: Path, gold_dir: Path, question_ids: list[str]) -> list[str]:
    """Every way the selected benchmark differs from what was frozen. Empty means the run may proceed."""
    problems: list[str] = []
    try:
        if questions_body_sha256(questions_path) not in (QUESTIONS_BODY_SHA256, EXT_QUESTIONS_BODY_SHA256):
            problems.append("the question file differs from the pre-registered question set and from the registered extension (D-39)")
    except (OSError, ValueError):
        problems.append("the question file could not be read as the pre-registered question set or the registered extension")
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != MANIFEST_SHA256:
        problems.append("the corpus manifest differs from the pre-registered manifest")
    if stamp_sha256() != PROTOCOL_STAMP_SHA256:
        problems.append("the retrieval protocol stamp changed (a frozen constant, D-20): needs a version bump and an ADR")
    for qid in question_ids:
        path = gold_dir / f"{qid}.yaml"
        if not path.exists():
            problems.append(f"{qid}: no gold file")
            continue
        if not yaml.safe_load(path.read_text(encoding="utf-8")).get("approved_by"):
            continue  # not approved: require_approved_gold reports it
        pinned = {**APPROVED_GOLD_SHA256, **APPROVED_EXT_GOLD_SHA256}.get(qid)
        if pinned is None:
            problems.append(f"{qid}: approved gold is not pinned")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != pinned:
            problems.append(f"{qid}: approved gold was edited after approval (a declared amendment is needed)")
    return problems
