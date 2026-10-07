"""The lab checker (P4 V2, D-36): what is accepted is listed by hand, and every planted defect (`api/labs/planted.py`) must be rejected by the
rule named for it. The allowlist file is the single list the checker reads; a test pins its key numbers to the guide."""

import json

import pytest

from api.labs.checker import ALLOWLIST_PATH, LabToolError, check_source
from api.labs.planted import GOOD, STATIC_DEFECTS, lab

PARAMS = ["si", "sj"]


def test_the_plain_ranknet_function_is_accepted():
    result = check_source(GOOD, PARAMS)
    assert result.ok and result.problems == ()


@pytest.mark.parametrize(
    "source",
    [
        lab(
            "  const d = p.sj - p.si;\n  if (d > 0) { return d + Math.log1p(Math.exp(-d)); }\n  return Math.log1p(Math.exp(d));"
        ),
        lab("let s = 0;\nfor (let i = 0; i < 10; i++) { s += Math.exp(-i); }\nreturn s;"),
        lab("let s = 0;\nfor (let i = 0; i <= 9; i += 1) { s = s + i * p.si; }\nreturn s;"),
        lab(
            "let s = 0;\nfor (let i = 0; i < 100; i++) { for (let j = 0; j < 100; j++) { s += 1; } }\nreturn s;"
        ),
        lab("const a = p.si > 0 ? p.si : -p.si;\nreturn a * Math.PI + Math.E;"),
        lab("let a = 1;\na++;\na *= 2;\nreturn a ** 2 % 3;"),
        lab("const ok = p.si < p.sj && !(p.sj < 0) || true;\nif (ok) return 1;\nreturn 0;"),
        lab("return Math.max(Math.min(p.si, p.sj), -1) + Math.hypot(1, 2);"),
    ],
    ids=[
        "stable_ranknet",
        "loop_sum",
        "loop_step",
        "nested_loops_within_budget",
        "ternary_constants",
        "update_and_assign",
        "logic_and_if",
        "math_calls",
    ],
)
def test_the_listed_constructs_are_accepted(source):
    result = check_source(source, PARAMS)
    assert result.ok, result.problems


@pytest.mark.parametrize("defect", STATIC_DEFECTS, ids=lambda d: d.name)
def test_every_planted_static_defect_is_rejected_by_the_rule_named_for_it(defect):
    result = check_source(defect.source, PARAMS)
    assert not result.ok, f"{defect.name} was accepted"
    assert defect.rule in result.rules, f"{defect.name}: wanted {defect.rule}, got {result.rules}"


def test_a_problem_says_where_and_why():
    result = check_source(lab("return p.constructor;"), PARAMS)
    problem = result.problems[0]
    assert (problem.rule, problem.line) == ("member_not_allowed", 2)
    assert "constructor" in problem.message


def test_the_parameters_allowed_are_the_ones_the_contract_declares():
    assert check_source(lab("return p.si + p.sj;"), ["si", "sj"]).ok
    refused = check_source(lab("return p.si + p.sj;"), ["si"])
    assert not refused.ok and "member_not_allowed" in refused.rules


def test_the_set_covers_every_kind_of_defect_it_claims_and_has_no_duplicate_names():
    names = [d.name for d in STATIC_DEFECTS]
    assert len(names) == len(set(names))
    assert {d.kind for d in STATIC_DEFECTS} >= {
        "network",
        "escape",
        "values",
        "operators",
        "statements",
        "termination",
        "resources",
        "shape",
        "markup",
    }
    assert len(STATIC_DEFECTS) >= 80


def test_the_allowlist_is_one_file_with_the_numbers_the_guide_states():
    allow = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    assert (allow["function_name"], allow["param_name"]) == ("lab", "p")
    assert (
        allow["max_source_chars"],
        allow["max_loop_bound"],
        allow["max_loop_depth"],
        allow["max_loop_product"],
    ) == (4000, 10000, 2, 100000)
    assert "random" not in allow["math_functions"]  # no randomness: the function is pure
    assert not {"fetch", "eval", "Function", "constructor"} & set(allow["math_functions"])


def test_a_missing_tool_is_a_refusal_not_a_pass(monkeypatch):
    monkeypatch.setattr("api.labs.checker.shutil.which", lambda _name: None)
    with pytest.raises(LabToolError):
        check_source(GOOD, PARAMS)
