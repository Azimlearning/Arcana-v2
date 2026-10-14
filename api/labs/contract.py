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
MIN_GRID = 4
MAX_GRID = 100
MAX_GRID_VECTORS = 10_000
"""The slider grid: each parameter takes `grid + 1` evenly spaced values and nothing between, and the verifier tests EVERY combination, so no
value the interface can ask the function for goes unchecked. The number of combinations is bounded."""
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
    """The parameter the plot sweeps across its range (at its grid values)."""
    grid: int
    """Steps per parameter: a slider has `grid + 1` positions. Defaults and reference cases lie on the grid."""
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
        if not MIN_GRID <= self.grid <= MAX_GRID:
            raise ValueError(f"the grid has {MIN_GRID} to {MAX_GRID} steps")
        if (self.grid + 1) ** len(names) > MAX_GRID_VECTORS:
            raise ValueError(
                f"the grid has more than {MAX_GRID_VECTORS} combinations: every one is verified"
            )
        for p in self.parameters:
            if not _on_grid(p, p.default, self.grid):
                raise ValueError(f"the default of {p.name} must lie on the grid")
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
                if not _on_grid(by_name[name], value, self.grid):
                    raise ValueError(f"a reference case's {name} must lie on the grid")
        for prop in self.properties:
            if prop.kind == "monotone" and prop.param not in names:
                raise ValueError("a monotone property names a declared parameter")
        return self

    def parameter(self, name: str) -> LabParameter:
        return next(p for p in self.parameters if p.name == name)

    @property
    def sweep_points(self) -> int:
        return self.grid + 1

    def grid_values(self, name: str) -> list[float]:
        """The values a slider can take: `grid + 1` evenly spaced values across the range, ends included, computed as `min + (max - min) * k / grid`
        (the web host computes the same expression in the same order, so both sides get the same doubles)."""
        p = self.parameter(name)
        return [grid_value(p, k, self.grid) for k in range(self.grid + 1)]

    def sweep_values(self) -> list[float]:
        """The sweep's x values: the swept parameter's grid values."""
        return self.grid_values(self.sweep)

    def defaults(self) -> dict[str, float]:
        return {p.name: p.default for p in self.parameters}


def grid_value(p: LabParameter, k: int, grid: int) -> float:
    return p.min + (p.max - p.min) * k / grid


def _on_grid(p: LabParameter, value: float, grid: int) -> bool:
    k = round((value - p.min) / (p.max - p.min) * grid)
    return 0 <= k <= grid and abs(grid_value(p, k, grid) - value) <= 1e-12 * max(1.0, abs(value))


# ── reference functions: written by hand from the cited formula, the verifier's ground truth ───────────────────────────


def ranknet_loss(si: float, sj: float) -> float:
    """The RankNet pairwise loss for one pair in which passage i is ranked before j: log(1 + exp(sj - si)), computed without overflow.
    (Burges et al., 2005, as the stored passage states it: L = sum_i sum_j 1[r_i < r_j] log(1 + exp(s_j - s_i)).)"""
    d = sj - si
    return d + math.log1p(math.exp(-d)) if d > 0 else math.log1p(math.exp(d))


def f1_at_k(hits: float, k: float, relevant: float) -> float:
    """F1@k from counts: precision@k is hits / k, recall@k is hits / relevant, and F1@k "the harmonic mean of precision and recall" (as the
    stored passage states). `hits` cannot exceed `k` (you retrieved k) or `relevant` (there are that many), so it is clamped to both."""
    h = min(hits, k, relevant)
    if h <= 0:
        return 0.0
    precision = h / k
    recall = h / relevant
    return 2 * precision * recall / (precision + recall)


def infonce_loss(phi_pos: float, phi_neg: float, negatives: float) -> float:
    """The InfoNCE loss as the stored passage prints it: -log( phi(t, r+) / ( phi(t, r+) + sum over the negatives of phi(t, n_i) ) ), here
    with the same similarity `phi_neg` for each of `negatives` negatives."""
    return -math.log(phi_pos / (phi_pos + negatives * phi_neg))


def cosine_chunk_distance(angle: float) -> float:
    """The semantic distance the passage's chunker uses: d = 1 - max(cos(emb(a), emb(b)), 0), with the angle between the two embeddings in degrees."""
    return 1.0 - max(math.cos(math.radians(angle)), 0.0)


REFERENCES: dict[str, Callable[..., float]] = {
    "ranknet_loss": ranknet_loss,
    "f1_at_k": f1_at_k,
    "infonce_loss": infonce_loss,
    "cosine_chunk_distance": cosine_chunk_distance,
}
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
        grid=64,
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


def f1_at_k_contract() -> LabContract:
    """F1@k from the number of relevant hits, k and the number of relevant documents. Evidence: the stored passage that defines F1@k as the
    harmonic mean of precision and recall (and, next to it, recall@k and precision@k as fractions)."""
    return LabContract(
        id="f1_at_k",
        title="F1@k: the harmonic mean of precision and recall",
        parameters=(
            LabParameter(name="hits", label="relevant documents among the k retrieved", min=0.0, max=20.0, default=3.0),
            LabParameter(name="k", label="documents retrieved (k)", min=1.0, max=21.0, default=10.0),
            LabParameter(name="relevant", label="relevant documents in the corpus", min=1.0, max=21.0, default=5.0),
        ),
        sweep="k",
        grid=20,
        output_label="F1@k",
        source_phrase="F1@k: The harmonic mean of precision and recall",
        reference="f1_at_k",
        cases=(
            ReferenceCase(params={"hits": 3.0, "k": 10.0, "relevant": 5.0}, expected=0.4, tolerance=1e-9),
            ReferenceCase(params={"hits": 5.0, "k": 5.0, "relevant": 5.0}, expected=1.0, tolerance=1e-9),
            ReferenceCase(params={"hits": 0.0, "k": 10.0, "relevant": 5.0}, expected=0.0, tolerance=1e-9),
            ReferenceCase(params={"hits": 8.0, "k": 10.0, "relevant": 4.0}, expected=4.0 / 7.0, tolerance=1e-9),
            ReferenceCase(params={"hits": 2.0, "k": 4.0, "relevant": 8.0}, expected=1.0 / 3.0, tolerance=1e-9),
        ),
        properties=(
            PropertySpec(kind="finite"),
            PropertySpec(kind="non_negative"),
            PropertySpec(kind="bounded", lo=0.0, hi=1.0),
            PropertySpec(kind="monotone", param="hits", direction="increasing"),
            PropertySpec(kind="matches_reference"),
        ),
    )


def infonce_contract() -> LabContract:
    """The InfoNCE loss for one positive and `negatives` equally similar negatives, as the stored passage prints it. Evidence: the sentence that
    introduces it (`using the InfoNCE loss, min L = ...`)."""
    return LabContract(
        id="infonce_loss",
        title="InfoNCE loss for one positive and several negatives",
        parameters=(
            LabParameter(name="phi_pos", label="similarity to the correct item", min=0.05, max=1.0, default=0.8),
            LabParameter(name="phi_neg", label="similarity to each wrong item", min=0.05, max=1.0, default=0.3),
            LabParameter(name="negatives", label="number of wrong items", min=0.0, max=19.0, default=5.0),
        ),
        sweep="negatives",
        grid=19,
        output_label="loss",
        source_phrase="using the InfoNCE loss, min L",
        reference="infonce_loss",
        cases=(
            ReferenceCase(params={"phi_pos": 0.8, "phi_neg": 0.3, "negatives": 5.0}, expected=math.log(2.3 / 0.8), tolerance=1e-9),
            ReferenceCase(params={"phi_pos": 1.0, "phi_neg": 0.05, "negatives": 0.0}, expected=0.0, tolerance=1e-9),
            ReferenceCase(params={"phi_pos": 0.5, "phi_neg": 0.5, "negatives": 1.0}, expected=math.log(2.0), tolerance=1e-9),
            ReferenceCase(params={"phi_pos": 0.25, "phi_neg": 1.0, "negatives": 10.0}, expected=math.log(41.0), tolerance=1e-9),
            ReferenceCase(params={"phi_pos": 0.05, "phi_neg": 0.05, "negatives": 19.0}, expected=math.log(20.0), tolerance=1e-9),
        ),
        properties=(
            PropertySpec(kind="finite"),
            PropertySpec(kind="non_negative"),
            PropertySpec(kind="monotone", param="phi_pos", direction="decreasing"),
            PropertySpec(kind="monotone", param="phi_neg", direction="increasing"),
            PropertySpec(kind="monotone", param="negatives", direction="increasing"),
            PropertySpec(kind="matches_reference"),
        ),
    )


def cosine_chunk_distance_contract() -> LabContract:
    """The distance a semantic chunker uses between two sentences' embeddings: 1 - max(cos, 0). Evidence: the stored passage that prints it
    (`dcos(xa, xb) = 1 - max(cos(emb(xa), emb(xb)), 0)`)."""
    return LabContract(
        id="cosine_chunk_distance",
        title="Cosine distance between two sentence embeddings (the chunker's distance)",
        parameters=(LabParameter(name="angle", label="angle between the two embeddings", min=0.0, max=180.0, default=60.0, unit="degrees"),),
        sweep="angle",
        grid=72,
        output_label="distance",
        source_phrase="dcos(xa, xb) = 1 −max(cos(emb(xa), emb(xb)), 0)",  # noqa: RUF001  (the stored passage uses U+2212)
        reference="cosine_chunk_distance",
        cases=(
            ReferenceCase(params={"angle": 0.0}, expected=0.0, tolerance=1e-9),
            ReferenceCase(params={"angle": 60.0}, expected=0.5, tolerance=1e-9),
            ReferenceCase(params={"angle": 45.0}, expected=1.0 - math.sqrt(0.5), tolerance=1e-9),
            ReferenceCase(params={"angle": 90.0}, expected=1.0, tolerance=1e-9),
            ReferenceCase(params={"angle": 150.0}, expected=1.0, tolerance=1e-9),
        ),
        properties=(
            PropertySpec(kind="finite"),
            PropertySpec(kind="non_negative"),
            PropertySpec(kind="bounded", lo=0.0, hi=1.0),
            PropertySpec(kind="monotone", param="angle", direction="increasing"),
            PropertySpec(kind="matches_reference"),
        ),
    )


CONTRACTS: dict[str, Callable[[], LabContract]] = {
    "ranknet_pairwise_loss": ranknet_contract,
    "f1_at_k": f1_at_k_contract,
    "infonce_loss": infonce_contract,
    "cosine_chunk_distance": cosine_chunk_distance_contract,
}
"""The labs the server knows how to make, by id."""
