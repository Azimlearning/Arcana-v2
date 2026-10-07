"""The lab verifier and the mint (P4 V3, D-36). A correct function passes; every execution, numeric and resource failure is refused with
its stage; the mint cannot be used outside the verifier; the store takes only a minted artifact and never serves a rejected one."""

import copy
import re
from pathlib import Path

import pytest

from api.labs.contract import ranknet_contract
from api.labs.planted import GOOD, STATIC_DEFECTS, lab
from api.labs.store import SqliteLabStore, StoredLab
from api.labs.verifier import (
    TEMPLATE_VERSION,
    MintRefused,
    VerificationFailed,
    VerifiedArtifact,
    verify,
)

CONTRACT = ranknet_contract()
STABLE = lab(
    "  const d = p.sj - p.si;\n"
    "  if (d > 0) { return d + Math.log1p(Math.exp(-d)); }\n"
    "  return Math.log1p(Math.exp(d));"
)


def stage_of(source: str) -> str:
    with pytest.raises(VerificationFailed) as refused:
        verify(CONTRACT, source)
    return refused.value.stage


def test_a_correct_function_passes_and_is_minted_with_its_hash_and_counts():
    artifact = verify(CONTRACT, GOOD)
    assert isinstance(artifact, VerifiedArtifact)
    assert artifact.contract_id == "ranknet_pairwise_loss"
    assert artifact.template_version == TEMPLATE_VERSION
    assert artifact.lab_id == f"ranknet_pairwise_loss-{artifact.source_sha256[:12]}"
    assert len(artifact.source_sha256) == 64
    assert (artifact.checked.reference_cases, artifact.checked.properties) == (4, 5)
    assert artifact.checked.fuzz_cases == 9 + 200  # the 3 x 3 corners and the seeded fuzz
    assert (
        verify(CONTRACT, STABLE).source_sha256 != artifact.source_sha256
    )  # another function, another artifact


def test_verifying_the_same_source_twice_gives_the_same_artifact():
    a, b = verify(CONTRACT, GOOD), verify(CONTRACT, GOOD)
    assert (a.lab_id, a.source_sha256, a.checked) == (b.lab_id, b.source_sha256, b.checked)


@pytest.mark.parametrize(
    ("source", "stage"),
    [
        (lab("return p.sj - p.si;"), "reference_cases"),  # the wrong formula
        (
            lab("return Math.log1p(Math.exp(p.sj - p.si)) + 0.001;"),
            "reference_cases",
        ),  # off by a constant
        (lab("return Math.log1p(Math.exp(p.si - p.sj));"), "reference_cases"),  # the scores swapped
        (lab("return Math.sqrt(-1);"), "finite"),  # NaN
        (lab("return 1 / 0;"), "finite"),  # Infinity
        (lab("return Math.exp(1000 + p.si);"), "finite"),  # overflow
    ],
    ids=["wrong_formula", "wrong_constant", "swapped_scores", "nan", "infinity", "overflow"],
)
def test_numeric_failures_are_refused_at_their_stage(source, stage):
    assert stage_of(source) == stage


def test_a_function_right_on_the_cases_but_wrong_elsewhere_is_caught_by_the_properties():
    # it returns the formula's value at the four reference cases and something else everywhere else
    sneaky = lab(
        "const d = p.sj - p.si;\n"
        "if (p.si === 0 && p.sj === 0) { return 0.6931471805599453; }\n"
        "if (p.si === 0 && p.sj === 1) { return 1.3132616875182228; }\n"
        "if (p.si === 1 && p.sj === -1) { return 0.12692801104297263; }\n"
        "if (p.si === -2 && p.sj === 2) { return 4.0181499279178; }\n"
        "return Math.abs(Math.sin(d * 5)) + 5;"
    )
    assert stage_of(sneaky) in {"monotone", "matches_reference"}


def test_a_function_that_fails_the_static_check_never_reaches_the_runner():
    assert stage_of(lab('return fetch("x");')) == "check"
    wanted = {"fetch", "eval", "constructor_chain", "while_true"}
    assert all(stage_of(d.source) == "check" for d in STATIC_DEFECTS if d.name in wanted)


def test_a_slow_function_is_stopped_by_the_time_limit(monkeypatch):
    monkeypatch.setattr("api.labs.verifier.PER_CALL_TIMEOUT_MS", 50)
    heavy = lab(
        "let s = 0;\n"
        "for (let i = 0; i < 10000; i++) { for (let j = 0; j < 10; j++) { s += Math.sin(i * j) * Math.cos(i + j); } }\n"
        "return s;"
    )
    assert stage_of(heavy) in {"run", "reference_cases"}


def test_the_mint_cannot_be_used_outside_the_verifier():
    with pytest.raises(MintRefused):
        VerifiedArtifact(
            lab_id="x",
            contract_id="x",
            title="x",
            parameters=(),
            source="x",
            source_sha256="x",
            template_version=1,
            checked=None,
        )
    with pytest.raises(MintRefused):
        VerifiedArtifact(_mint=object(), lab_id="x")
    artifact = verify(CONTRACT, GOOD)
    with pytest.raises(AttributeError):
        artifact.source = "function lab(p) { return 1; }"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        del artifact.source
    with pytest.raises(AttributeError):
        copy.copy(artifact)  # not copyable either: a copy would be built by assignment
    with pytest.raises(AttributeError):
        copy.deepcopy(artifact)


def test_no_module_but_the_verifier_builds_a_verified_artifact_or_touches_the_mint():
    root = Path(__file__).resolve().parents[2]
    offenders = []
    for path in list((root / "api").rglob("*.py")) + list((root / "eval").rglob("*.py")):
        if path.name in {"verifier.py", "test_verifier.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"VerifiedArtifact\s*\(|\b_MINT\b", text):
            offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"these build a VerifiedArtifact or use the mint token: {offenders}"


def test_the_store_takes_only_a_minted_artifact_and_serves_only_verified_labs(tmp_path: Path):
    store = SqliteLabStore(tmp_path / "labs.db")
    artifact = verify(CONTRACT, GOOD)
    stored = store.put_verified(artifact)
    assert isinstance(stored, StoredLab) and not isinstance(stored, VerifiedArtifact)
    assert (stored.lab_id, stored.source, stored.source_sha256, stored.state) == (
        artifact.lab_id,
        GOOD,
        artifact.source_sha256,
        "verified",
    )
    assert store.get(artifact.lab_id) == stored
    assert store.get("ranknet_pairwise_loss-000000000000") is None
    with pytest.raises(TypeError):
        store.put_verified(stored)  # type: ignore[arg-type]
    store.put_rejected(CONTRACT.id, "function lab(p) { return 1; }", "reference_cases", "wrong")
    assert [r["contract_id"] for r in store.rejected()] == ["ranknet_pairwise_loss"]
    assert all(
        store.get(f"rejected-{r['source_sha256'][:16]}") is None for r in store.rejected()
    )  # never served
    assert SqliteLabStore(tmp_path / "labs.db").get(artifact.lab_id) == stored  # survives reopening
