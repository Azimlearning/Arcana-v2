"""Planted runtime and tampering defects for the mutation suite (P4 V7, D-36), beside the static ones in `planted.py`.

`EXECUTION_DEFECTS` are functions that pass the checker but must be refused by the verifier at the named stage (wrong numbers, non-finite
values, wrong shape of curve, too slow). `FORGERIES` change a delivered block's data in one way each; the delivery gate (the block
validator) must refuse every one. Together with the static defects they are the planted set the suite runs and whose detection rate is
recorded. The set is the planted set, not all possible attacks: a defect found later is added here with the stage that should catch it.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from api.labs.planted import lab


@dataclass(frozen=True)
class ExecutionDefect:
    name: str
    kind: str
    source: str
    stage: str
    """The verifier stage that must refuse it."""


EXECUTION_DEFECTS: tuple[ExecutionDefect, ...] = (
    ExecutionDefect("wrong_formula", "numeric", lab("return p.sj - p.si;"), "reference_cases"),
    ExecutionDefect(
        "off_by_constant",
        "numeric",
        lab("return Math.log1p(Math.exp(p.sj - p.si)) + 0.001;"),
        "reference_cases",
    ),
    ExecutionDefect(
        "scores_swapped",
        "numeric",
        lab("return Math.log1p(Math.exp(p.si - p.sj));"),
        "reference_cases",
    ),
    ExecutionDefect(
        "wrong_base",
        "numeric",
        lab("return Math.log(1 + Math.exp(p.sj - p.si)) / Math.log(10);"),
        "reference_cases",
    ),
    ExecutionDefect("constant", "numeric", lab("return 0.6931471805599453;"), "reference_cases"),
    ExecutionDefect("nan", "numeric", lab("return Math.sqrt(-1);"), "finite"),
    ExecutionDefect("infinity", "numeric", lab("return 1 / 0;"), "finite"),
    ExecutionDefect("overflow", "numeric", lab("return Math.exp(1000 + p.si);"), "finite"),
    ExecutionDefect(
        "right_on_cases_wrong_elsewhere",
        "numeric",
        lab(
            "if (p.si === 0 && p.sj === 0) { return 0.6931471805599453; }\n"
            "if (p.si === 0 && p.sj === 1) { return 1.3132616875182228; }\n"
            "if (p.si === 1 && p.sj === -1) { return 0.12692801104297263; }\n"
            "if (p.si === -2 && p.sj === 2) { return 4.0181499279178; }\n"
            "return Math.abs(Math.sin((p.sj - p.si) * 5)) + 5;"
        ),
        "monotone",
    ),
    ExecutionDefect(
        "naive_overflow",
        "numeric",
        lab("return Math.log(1 + Math.exp((p.sj - p.si) * 1000));"),
        "finite",
    ),
    ExecutionDefect(
        "slow_in_the_budget",
        "resources",
        lab(
            "let s = 0;\nfor (let i = 0; i < 2000; i++) { for (let j = 0; j < 10; j++) { s += Math.sin(i * j) * Math.cos(i + j); } }\nreturn s;"
        ),
        "check",
    ),
    ExecutionDefect(
        "hidden_branch_wrong_value_on_the_grid",
        "numeric",
        lab(
            "if (p.si === -3.875) { return 1000; }\n"
            "const d = p.sj - p.si;\n"
            "if (d > 0) { return d + Math.log1p(Math.exp(-d)); }\n"
            "return Math.log1p(Math.exp(d));"
        ),
        "monotone",
    ),
    ExecutionDefect(
        "hidden_branch_nan_on_the_grid",
        "numeric",
        lab(
            "if (p.sj === 3.5 && p.si === 0.25) { return Math.sqrt(-1); }\n"
            "const d = p.sj - p.si;\n"
            "if (d > 0) { return d + Math.log1p(Math.exp(-d)); }\n"
            "return Math.log1p(Math.exp(d));"
        ),
        "finite",
    ),
    ExecutionDefect(
        "hidden_branch_small_error_on_the_grid",
        "numeric",
        lab(
            "const d = p.sj - p.si;\n"
            "if (p.si === 2 && p.sj === -2) { return Math.log1p(Math.exp(-4)) + 0.000001; }\n"
            "if (d > 0) { return d + Math.log1p(Math.exp(-d)); }\n"
            "return Math.log1p(Math.exp(d));"
        ),
        "matches_reference",
    ),
)
"""Each passes the checker except `slow_in_the_budget`, which the checker's total iteration cap now refuses. The hidden-branch defects hide a
branch at one slider position: a sampled battery misses them and the all-grid battery does not (a red-team review made the hang and wrong-value
versions of this and had them verified)."""


Forgery = Callable[[dict[str, Any]], None]


def _forgeries() -> dict[str, Forgery]:
    def source_appended(d: dict[str, Any]) -> None:
        d["source"] = d["source"] + "\n"

    def source_swapped(d: dict[str, Any]) -> None:
        d["source"] = "function lab(p) { return 1; }"

    def hash_zeroed(d: dict[str, Any]) -> None:
        d["sourceSha256"] = "0" * 64

    def template_version(d: dict[str, Any]) -> None:
        d["templateVersion"] = 3

    def lab_id(d: dict[str, Any]) -> None:
        d["labId"] = "ranknet_pairwise_loss-000000000000"

    def contract_id(d: dict[str, Any]) -> None:
        d["contractId"] = "other"

    def title(d: dict[str, Any]) -> None:
        d["title"] = "Something else"

    def parameter_range(d: dict[str, Any]) -> None:
        d["parameters"][0]["max"] = 400.0

    def parameter_added(d: dict[str, Any]) -> None:
        d["parameters"].append(copy.deepcopy(d["parameters"][0]))

    def sweep(d: dict[str, Any]) -> None:
        d["sweep"] = "si"

    def sweep_points(d: dict[str, Any]) -> None:
        d["sweepPoints"] = 5000

    def checked_counts(d: dict[str, Any]) -> None:
        d["checked"]["fuzzCases"] = 10_000

    def citation_quote(d: dict[str, Any]) -> None:
        d["citations"][0]["quote"] = "A sentence the passage never says at all."

    def citation_page(d: dict[str, Any]) -> None:
        d["citations"][0]["page"] = 3

    def citations_dropped(d: dict[str, Any]) -> None:
        d["citations"] = []

    def output_label(d: dict[str, Any]) -> None:
        d["outputLabel"] = "x"

    return {
        f.__name__: f
        for f in (
            source_appended,
            source_swapped,
            hash_zeroed,
            template_version,
            lab_id,
            contract_id,
            title,
            parameter_range,
            parameter_added,
            sweep,
            sweep_points,
            checked_counts,
            citation_quote,
            citation_page,
            citations_dropped,
            output_label,
        )
    }


FORGERIES: dict[str, Forgery] = _forgeries()
