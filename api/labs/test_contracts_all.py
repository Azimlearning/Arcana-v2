"""Every contract the server knows (P4, D-36): its reference cases are the formula by hand, a hand-written function for it passes the verifier,
a wrong one is refused, and the list of labs says which ones the stored passages support.

Reference values worked out by hand:
    f1_at_k: hits 3, k 10, relevant 5 -> P 0.3, R 0.6, F1 = 2 * 0.18 / 0.9 = 0.4; hits 8, k 10, relevant 4 -> hits clamp to 4, P 0.4, R 1,
             F1 = 0.8 / 1.4 = 4/7; hits 2, k 4, relevant 8 -> P 0.5, R 0.25, F1 = 0.25 / 0.75 = 1/3
    infonce: 0.8, 0.3, 5 negatives -> -ln(0.8 / 2.3) = ln 2.875; 0.5, 0.5, 1 -> ln 2; 0.25, 1, 10 -> ln 41; 0.05, 0.05, 19 -> ln 20
    cosine distance: 0 deg -> 0; 60 deg -> 1 - 0.5; 45 deg -> 1 - sqrt(1/2); 90 and 150 deg -> 1 (cos <= 0 is clamped to 0)
"""

import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.core.settings import Settings
from api.labs.contract import CONTRACTS, REFERENCES, cosine_chunk_distance, f1_at_k, infonce_loss
from api.labs.generator import FakeLabGenerator
from api.labs.planted import lab
from api.labs.verifier import VerificationFailed, verify
from api.main import create_app
from api.stores.doc_store import Chunk, Document

PASSAGES = {
    "ranknet_pairwise_loss": "RankNet is a pairwise loss that measures the correctness of relative passage orders: L = sum log(1 + exp(sj - si)).",
    "f1_at_k": "Metrics. Recall@k: Fraction of relevant documents retrieved. F1@k: The harmonic mean of precision and recall. In typical experiments.",
    "infonce_loss": "We finetune the model using the InfoNCE loss, min L = -log phi(t, r+) / (phi(t, r+) + sum phi(t, ni)) here N denotes negatives.",
    "cosine_chunk_distance": "The distance is dcos(xa, xb) = 1 −max(cos(emb(xa), emb(xb)), 0) (3) where n is the number of sentences.",  # noqa: RUF001
}


@pytest.mark.parametrize("contract_id", list(CONTRACTS))
def test_the_known_function_passes_and_the_contract_matches_its_reference(contract_id):
    contract = CONTRACTS[contract_id]()
    reference = REFERENCES[contract.reference]
    for case in contract.cases:
        assert reference(**case.params) == pytest.approx(case.expected, abs=case.tolerance)
    artifact = verify(contract, FakeLabGenerator().generate(contract))
    assert artifact.contract_id == contract_id
    assert artifact.checked.grid_points == (contract.grid + 1) ** len(contract.parameters)
    assert artifact.checked.reference_cases == len(contract.cases)


def test_the_reference_values_are_the_formulas_by_hand():
    assert f1_at_k(3, 10, 5) == pytest.approx(0.4)
    assert f1_at_k(8, 10, 4) == pytest.approx(4 / 7)  # hits clamp to the 4 relevant documents
    assert f1_at_k(2, 4, 8) == pytest.approx(1 / 3)
    assert f1_at_k(0, 10, 5) == 0.0 and f1_at_k(5, 5, 5) == pytest.approx(1.0)
    assert infonce_loss(0.8, 0.3, 5) == pytest.approx(math.log(2.875))
    assert infonce_loss(0.5, 0.5, 1) == pytest.approx(math.log(2))
    assert infonce_loss(1.0, 0.05, 0) == pytest.approx(0.0)
    assert cosine_chunk_distance(60) == pytest.approx(0.5)
    assert cosine_chunk_distance(45) == pytest.approx(1 - math.sqrt(0.5))
    assert cosine_chunk_distance(120) == 1.0


@pytest.mark.parametrize(
    ("contract_id", "wrong", "stage"),
    [
        ("f1_at_k", lab("return p.hits / p.k;"), "reference_cases"),  # precision, not F1
        (
            "f1_at_k",
            lab("const h = Math.min(p.hits, p.k, p.relevant);\nreturn h / p.relevant;"),
            "reference_cases",
        ),  # recall only
        (
            "infonce_loss",
            lab("return Math.log(1 + p.negatives * p.phi_pos / p.phi_neg);"),
            "reference_cases",
        ),  # the ratio inverted
        (
            "infonce_loss",
            lab("return -Math.log(p.phi_pos);"),
            "reference_cases",
        ),  # the negatives forgotten
        (
            "cosine_chunk_distance",
            lab("return 1 - Math.cos(p.angle * Math.PI / 180);"),
            "reference_cases",
        ),  # no clamp at 0
        (
            "cosine_chunk_distance",
            lab("return Math.sin(p.angle * Math.PI / 180);"),
            "reference_cases",
        ),
    ],
)
def test_a_wrong_function_for_each_new_contract_is_refused(contract_id, wrong, stage):
    with pytest.raises(VerificationFailed) as refused:
        verify(CONTRACTS[contract_id](), wrong)
    assert refused.value.stage == stage


def test_the_lab_list_says_which_labs_the_stored_passages_support(tmp_path: Path):
    settings = Settings(_env_file=None, arcana_data_dir=tmp_path / "data")  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as client:
        empty = client.get("/labs").json()["labs"]
        assert {entry["contractId"] for entry in empty} == set(CONTRACTS)
        assert all(not entry["available"] and entry["reason"] and entry["page"] is None for entry in empty)
        container = client.app.state.container  # type: ignore[attr-defined]
        container.docs.put_document(
            Document("d1", "A Paper", "d1.pdf", "ready", 1, None, "2026-10-14")
        )
        container.docs.put_chunks(
            [
                Chunk("c1", "d1", 0, 9, PASSAGES["f1_at_k"]),
                Chunk("c2", "d1", 1, 13, PASSAGES["infonce_loss"]),
            ]
        )
        listed = {entry["contractId"]: entry for entry in client.get("/labs").json()["labs"]}
        assert (
            listed["f1_at_k"]["available"]
            and listed["f1_at_k"]["page"] == 9
            and listed["f1_at_k"]["docTitle"] == "A Paper"
        )
        assert listed["infonce_loss"]["available"] and listed["infonce_loss"]["page"] == 13
        assert (
            not listed["ranknet_pairwise_loss"]["available"]
            and "No stored passage" in listed["ranknet_pairwise_loss"]["reason"]
        )
        made = client.post("/labs", json={"contractId": "f1_at_k"}).json()["blocks"][0]
        assert (made["type"], made["meta"]["status"]) == ("VerifiedLab", "ready")
        assert made["data"]["checked"]["gridPoints"] == 21**3
        unsupported = client.post("/labs", json={"contractId": "ranknet_pairwise_loss"}).json()[
            "blocks"
        ][0]
        assert (
            unsupported["meta"]["status"] == "empty"
        )  # no passage states it: no lab, said as such
