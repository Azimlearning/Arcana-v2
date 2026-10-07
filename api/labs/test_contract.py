"""The lab contract (P4 V1, D-36): a declaration is checked when it is made, and the built-in RankNet contract agrees with its own
reference function on every case, by hand: log 2 for equal scores, log(1 + e) for a difference of 1, log(1 + e^-2) for -2 and log(1 + e^4) for 4."""

import math
from itertools import pairwise

import pytest
from pydantic import ValidationError

from api.labs.contract import (
    CONTRACTS,
    MAX_PARAMETERS,
    REFERENCES,
    LabContract,
    LabParameter,
    PropertySpec,
    ReferenceCase,
    ranknet_contract,
    ranknet_loss,
)


def parameter(**over):
    base = {"name": "x", "label": "x", "min": 0.0, "max": 1.0, "default": 0.5}
    return LabParameter(**{**base, **over})


def contract(**over):
    base = {
        "id": "demo_lab",
        "title": "A demo",
        "parameters": (parameter(),),
        "sweep": "x",
        "grid": 16,
        "output_label": "value",
        "source_phrase": "a phrase that is long enough to cite",
        "reference": "ranknet_loss",
        "cases": (ReferenceCase(params={"x": 0.5}, expected=0.0, tolerance=1e-9),),
        "properties": (PropertySpec(kind="finite"),),
    }
    return LabContract(**{**base, **over})


def test_the_builtin_ranknet_contract_is_valid_and_registered():
    c = ranknet_contract()
    assert CONTRACTS["ranknet_pairwise_loss"]().id == c.id == "ranknet_pairwise_loss"
    assert (
        [p.name for p in c.parameters] == ["si", "sj"]
        and c.sweep == "sj"
        and c.defaults() == {"si": 0.0, "sj": 1.0}
    )


def test_the_reference_cases_are_the_formula_by_hand():
    c = ranknet_contract()
    expected = [
        math.log(2),
        math.log(1 + math.e),
        math.log(1 + math.exp(-2)),
        math.log(1 + math.exp(4)),
    ]
    assert [case.expected for case in c.cases] == pytest.approx(expected, abs=1e-12)
    for case in c.cases:
        assert ranknet_loss(**case.params) == pytest.approx(case.expected, abs=case.tolerance)
        assert REFERENCES[c.reference](**case.params) == pytest.approx(
            case.expected, abs=case.tolerance
        )


def test_the_reference_does_not_overflow_and_has_the_stated_shape():
    assert math.isfinite(ranknet_loss(-1000.0, 1000.0)) and ranknet_loss(
        -1000.0, 1000.0
    ) == pytest.approx(2000.0)
    assert ranknet_loss(1000.0, -1000.0) == pytest.approx(0.0, abs=1e-300)
    values = [ranknet_loss(0.0, sj / 10) for sj in range(-40, 41)]
    assert all(b > a for a, b in pairwise(values))  # strictly increasing in sj
    assert all(v >= 0 for v in values)
    assert (
        ranknet_loss(1.0, 0.0) < ranknet_loss(0.0, 0.0) < ranknet_loss(-1.0, 0.0)
    )  # decreasing in si


def test_the_sweep_has_the_declared_points_across_the_range_ends_included():
    c = ranknet_contract()
    xs = c.sweep_values()
    assert len(xs) == 65 and xs[0] == -4.0 and xs[-1] == 4.0 and xs[32] == 0.0 and xs[1] == -3.875


@pytest.mark.parametrize(
    "make",
    [
        lambda: parameter(name="Bad Name"),
        lambda: parameter(name="1x"),
        lambda: parameter(min=1.0, max=1.0),
        lambda: parameter(min=2.0, max=1.0),
        lambda: parameter(default=2.0),
        lambda: parameter(max=math.inf),
        lambda: parameter(default=math.nan),
        lambda: ReferenceCase(params={"x": 0.5}, expected=math.nan, tolerance=1e-9),
        lambda: ReferenceCase(params={"x": 0.5}, expected=0.0, tolerance=0.0),
        lambda: ReferenceCase(params={"x": math.inf}, expected=0.0, tolerance=1e-9),
        lambda: PropertySpec(kind="monotone"),
        lambda: PropertySpec(kind="bounded", lo=1.0, hi=0.0),
        lambda: contract(parameters=()),
        lambda: contract(
            parameters=tuple(parameter(name=f"p{i}") for i in range(MAX_PARAMETERS + 1)), sweep="p0"
        ),
        lambda: contract(parameters=(parameter(), parameter())),
        lambda: contract(sweep="y"),
        lambda: contract(grid=3),
        lambda: contract(grid=5000),
        lambda: contract(parameters=(parameter(default=0.51),)),
        lambda: contract(cases=(ReferenceCase(params={"x": 0.51}, expected=0.0, tolerance=1e-9),)),
        lambda: contract(source_phrase="too short"),
        lambda: contract(reference="nothing"),
        lambda: contract(cases=()),
        lambda: contract(cases=(ReferenceCase(params={"y": 0.5}, expected=0.0, tolerance=1e-9),)),
        lambda: contract(cases=(ReferenceCase(params={"x": 5.0}, expected=0.0, tolerance=1e-9),)),
        lambda: contract(
            properties=(PropertySpec(kind="monotone", param="y", direction="increasing"),)
        ),
        lambda: contract(id="Bad-Id"),
    ],
    ids=lambda f: str(abs(hash(f)) % 10_000),
)
def test_a_malformed_declaration_is_refused(make):
    with pytest.raises((ValidationError, ValueError)):
        make()


def test_a_contract_is_immutable_and_refuses_unknown_fields():
    c = ranknet_contract()
    with pytest.raises(ValidationError):
        c.title = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        LabContract(**{**c.model_dump(), "run_this": "code"})
