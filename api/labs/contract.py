"""A lab's contract (P4 V1, D-36): what a generated function promises, as data the verifier can check.

A lab is one pure function `lab(p)` from a few declared parameters to one number. The interactive part (sliders, a plot of the number
as one parameter sweeps its range) is a fixed template; only the function is generated. The contract declares:

- the parameters (at most four, each with a finite range and a default), and which one the plot sweeps;
- the evidence: a phrase that must occur in a stored passage (the sentence that states the formula), found at generation time, so a
  contract can only be used over a corpus that actually holds its formula;
- reference cases (parameters and the number the formula gives, with a tolerance), written by hand from the formula;
- properties that must hold over the whole declared range (finite, non-negative, bounded, monotone in a parameter) and a reference
  function the generated one must agree with everywhere it is tested.

Nothing here runs generated code. The checker and the verifier (later tasks) read a contract; they never trust the function.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

MAX_PARAMETERS = 4
MIN_SWEEP_POINTS = 8
MAX_SWEEP_POINTS = 200
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,15}$")

PropertyKind = Literal["finite", "non_negative", "bounded", "monotone", "matches_reference"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class LabParameter(_Frozen):
    name: str
    label: str
    min: float
    max: float
    default: float
    unit: str | None = None

    @field_validator("name")
    @classmethod
    def _identifier(cls, value: str) -> str:
        if not _NAME.match(value):
            raise ValueError("a parameter name is a lowercase identifier of at most 16 characters")
        return value

    @model_validator(mode="after")
    def _range(self) -> LabParameter:
        for field in ("min", "max", "default"):
            if not math.isfinite(getattr(self, field)):
                raise ValueError(f"{field} must be finite")
        if not self.min < self.max:
            raise ValueError("min must be below max")
        if not self.min <= self.default <= self.max:
            raise ValueError("default must lie in [min, max]")
        return self


class ReferenceCase(_Frozen):
    params: dict[str, float]
    expected: float
    tolerance: float

    @model_validator(mode="after")
    def _finite(self) -> ReferenceCase:
        if not math.isfinite(self.expected) or not (
            self.tolerance > 0 and math.isfinite(self.tolerance)
        ):
            raise ValueError(
                "a reference case needs a finite expected value and a positive tolerance"
            )
        if any(not math.isfinite(v) for v in self.params.values()):
            raise ValueError("a reference case's parameters must be finite")
        return self


class PropertySpec(_Frozen):
    kind: PropertyKind
    param: str | None = None
    """`monotone`: the parameter the number is monotone in (the others held fixed)."""
    direction: Literal["increasing", "decreasing"] | None = None
    lo: float | None = None
    hi: float | None = None
    """`bounded`: the number lies in [lo, hi]."""

    @model_validator(mode="after")
    def _complete(self) -> PropertySpec:
        if self.kind == "monotone" and (self.param is None or self.direction is None):
            raise ValueError("a monotone property names a parameter and a direction")
        if self.kind == "bounded" and (self.lo is None or self.hi is None or not self.lo < self.hi):
            raise ValueError("a bounded property needs lo below hi")
        return self


class LabContract(_Frozen):
    id: str
    title: str
    parameters: tuple[LabParameter, ...]
    sweep: str
    """The parameter the plot sweeps across its range."""
    sweep_points: int
    output_label: str
    source_phrase: str
    """A phrase that must occur (whitespace-normalised, hyphen-blind) in a stored passage: the evidence that states the formula."""
    reference: str
    """The key of the Python reference function (see `REFERENCES`) the generated function must agree with."""
    cases: tuple[ReferenceCase, ...]
    properties: tuple[PropertySpec, ...]
    agreement_tolerance: float = 1e-9

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]{2,40}$", value):
            raise ValueError("a lab id is a lowercase identifier")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> LabContract:
        names = [p.name for p in self.parameters]
        if not 1 <= len(names) <= MAX_PARAMETERS:
            raise ValueError(f"a lab has 1 to {MAX_PARAMETERS} parameters")
        if len(set(names)) != len(names):
            raise ValueError("parameter names must be unique")
        if self.sweep not in names:
            raise ValueError("the swept parameter must be one of the parameters")
        if not MIN_SWEEP_POINTS <= self.sweep_points <= MAX_SWEEP_POINTS:
            raise ValueError(f"a sweep has {MIN_SWEEP_POINTS} to {MAX_SWEEP_POINTS} points")
        if not self.source_phrase.strip() or len(self.source_phrase) < 20:
            raise ValueError(
                "a lab cites evidence: the source phrase must be at least 20 characters"
            )
        if self.reference not in REFERENCES:
            raise ValueError(f"unknown reference function {self.reference!r}")
        if not self.cases:
            raise ValueError("a lab needs at least one reference case")
        by_name = {p.name: p for p in self.parameters}
        for case in self.cases:
            if set(case.params) != set(names):
                raise ValueError("a reference case gives exactly the declared parameters")
            for name, value in case.params.items():
                if not by_name[name].min <= value <= by_name[name].max:
                    raise ValueError(f"a reference case's {name} lies outside its range")
        for prop in self.properties:
            if prop.kind == "monotone" and prop.param not in names:
                raise ValueError("a monotone property names a declared parameter")
        return self

    def parameter(self, name: str) -> LabParameter:
        return next(p for p in self.parameters if p.name == name)

    def sweep_values(self) -> list[float]:
        """The sweep's x values: `sweep_points` evenly spaced values across the swept parameter's range, ends included."""
        p = self.parameter(self.sweep)
        n = self.sweep_points
        return [p.min + (p.max - p.min) * i / (n - 1) for i in range(n)]

    def defaults(self) -> dict[str, float]:
        return {p.name: p.default for p in self.parameters}


# ── reference functions: written by hand from the cited formula, the verifier's ground truth ───────────────────────────


def ranknet_loss(si: float, sj: float) -> float:
    """The RankNet pairwise loss for one pair in which passage i is ranked before j: log(1 + exp(sj - si)), computed without overflow.
    (Burges et al., 2005, as the stored passage states it: L = sum_i sum_j 1[r_i < r_j] log(1 + exp(s_j - s_i)).)"""
    d = sj - si
    return d + math.log1p(math.exp(-d)) if d > 0 else math.log1p(math.exp(d))


REFERENCES: dict[str, Callable[..., float]] = {"ranknet_loss": ranknet_loss}
"""Reference functions by key; a contract names one. Adding a lab means adding its reference here, written from the cited formula."""


def ranknet_contract() -> LabContract:
    """The first contract (V1 probe, `refdocs/evidence/20261008-p4-v1-formula-probe.md`): the RankNet pairwise loss for one pair, with the
    score of the passage ranked first (`si`) and of the one ranked second (`sj`). The loss is small when `si` exceeds `sj` and grows
    without bound as `sj` exceeds `si`."""
    return LabContract(
        id="ranknet_pairwise_loss",
        title="RankNet pairwise loss for one pair of passages",
        parameters=(
            LabParameter(
                name="si", label="score of the passage ranked first", min=-4.0, max=4.0, default=0.0
            ),
            LabParameter(
                name="sj",
                label="score of the passage ranked second",
                min=-4.0,
                max=4.0,
                default=1.0,
            ),
        ),
        sweep="sj",
        sweep_points=65,
        output_label="loss",
        source_phrase="RankNet is a pairwise loss that measures the correctness of relative passage orders",
        reference="ranknet_loss",
        cases=(
            ReferenceCase(params={"si": 0.0, "sj": 0.0}, expected=math.log(2.0), tolerance=1e-9),
            ReferenceCase(
                params={"si": 0.0, "sj": 1.0}, expected=1.3132616875182228, tolerance=1e-9
            ),
            ReferenceCase(
                params={"si": 1.0, "sj": -1.0}, expected=0.12692801104297263, tolerance=1e-9
            ),
            ReferenceCase(
                params={"si": -2.0, "sj": 2.0}, expected=4.01814992791780, tolerance=1e-9
            ),
        ),
        properties=(
            PropertySpec(kind="finite"),
            PropertySpec(kind="non_negative"),
            PropertySpec(kind="monotone", param="sj", direction="increasing"),
            PropertySpec(kind="monotone", param="si", direction="decreasing"),
            PropertySpec(kind="matches_reference"),
        ),
    )


CONTRACTS: dict[str, Callable[[], LabContract]] = {"ranknet_pairwise_loss": ranknet_contract}
"""The labs the server knows how to make, by id."""
