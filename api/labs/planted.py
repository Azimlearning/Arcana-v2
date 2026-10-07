"""Planted static defects for the lab checker (P4 V2/V7, D-36): sources a generated function must never be allowed to have.

Each entry is (name, class, source, the rule that must reject it). The checker's test runs every one; the mutation suite (V7) runs the
same set together with the execution, numeric and tampering defects and records the detection rate. The set is the planted set, not
all possible attacks: a defect found later is added here with the rule that should have caught it.

Parameters in every source are the RankNet contract's `si` and `sj`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Planted:
    name: str
    kind: str
    source: str
    rule: str
    """The checker rule that must be among the problems found."""


def lab(body: str) -> str:
    return "function lab(p) {\n" + body + "\n}"


GOOD = lab("  const d = p.sj - p.si;\n  return Math.log1p(Math.exp(d));")

STATIC_DEFECTS: tuple[Planted, ...] = (
    # network
    Planted("fetch", "network", lab('return fetch("https://example.com");'), "call_not_allowed"),
    Planted(
        "xhr", "network", lab("const x = new XMLHttpRequest(); return 1;"), "node_type_not_allowed"
    ),
    Planted(
        "websocket",
        "network",
        lab('const w = new WebSocket("ws://x"); return 1;'),
        "node_type_not_allowed",
    ),
    Planted(
        "dynamic_import",
        "network",
        lab('return import("https://example.com/x.js");'),
        "node_type_not_allowed",
    ),
    Planted("require", "network", lab('return require("http");'), "call_not_allowed"),
    # escape routes to globals, prototypes and constructors
    Planted(
        "constructor_chain",
        "escape",
        lab('return p.constructor.constructor("return 1")();'),
        "call_not_allowed",
    ),
    Planted("global_this", "escape", lab("return globalThis.x;"), "member_not_allowed"),
    Planted("this", "escape", lab("return this.x;"), "member_not_allowed"),
    Planted("proto", "escape", lab("return p.__proto__;"), "member_not_allowed"),
    Planted("function_ctor", "escape", lab('return Function("return 1")();'), "call_not_allowed"),
    Planted("eval", "escape", lab('return eval("1");'), "call_not_allowed"),
    Planted("process", "escape", lab("return process.exit();"), "call_not_allowed"),
    Planted("window", "escape", lab("return window.parent;"), "member_not_allowed"),
    Planted("arguments", "escape", lab("return arguments[0];"), "member_not_allowed"),
    Planted("math_constructor", "escape", lab("return Math.constructor;"), "member_not_allowed"),
    Planted("math_computed", "escape", lab('return Math["sin"](1);'), "call_not_allowed"),
    Planted("math_unlisted", "escape", lab("return Math.random();"), "call_not_allowed"),
    Planted("computed_member", "escape", lab('return p["si"];'), "member_not_allowed"),
    Planted("optional_chain", "escape", lab("return p?.si;"), "node_type_not_allowed"),
    Planted(
        "denied_name_constructor",
        "escape",
        lab("const constructor = 1; return constructor;"),
        "name_not_allowed",
    ),
    Planted(
        "denied_name_escaped",
        "escape",
        lab("const \\u0063onstructor = 1; return 1;"),
        "name_not_allowed",
    ),
    Planted("param_alone", "escape", lab("const q = p; return 1;"), "identifier_not_allowed"),
    Planted("assign_param", "escape", lab("p.si = 1; return 1;"), "assignment_not_allowed"),
    Planted("undeclared_param", "escape", lab("return p.zz;"), "member_not_allowed"),
    Planted("undeclared_name", "escape", lab("return q;"), "identifier_not_allowed"),
    # values that are not numbers
    Planted("string", "values", lab('const s = "a"; return 1;'), "literal_not_allowed"),
    Planted("template", "values", lab("const s = `a`; return 1;"), "node_type_not_allowed"),
    Planted("regex", "values", lab("const r = /a/; return 1;"), "literal_not_allowed"),
    Planted("bigint", "values", lab("return 1n;"), "literal_not_allowed"),
    Planted("array", "values", lab("const a = [1]; return 1;"), "node_type_not_allowed"),
    Planted("object", "values", lab("const o = {}; return 1;"), "node_type_not_allowed"),
    Planted("arrow", "values", lab("const f = (x) => x; return 1;"), "node_type_not_allowed"),
    Planted(
        "inner_function",
        "values",
        lab("function inner() { return 1; } return 1;"),
        "node_type_not_allowed",
    ),
    Planted("nan_name", "values", lab("return NaN;"), "identifier_not_allowed"),
    Planted("undefined_name", "values", lab("return undefined;"), "identifier_not_allowed"),
    # operators and statements
    Planted("typeof", "operators", lab("return typeof p.si;"), "operator_not_allowed"),
    Planted("delete", "operators", lab("return delete p.si;"), "operator_not_allowed"),
    Planted("void", "operators", lab("return void 0;"), "operator_not_allowed"),
    Planted("in", "operators", lab("return 1 in p;"), "operator_not_allowed"),
    Planted("instanceof", "operators", lab("return 1 instanceof p;"), "operator_not_allowed"),
    Planted("bitwise_or", "operators", lab("return 1 | 2;"), "operator_not_allowed"),
    Planted(
        "exp_assign", "operators", lab("let a = 2; a **= 2; return a;"), "operator_not_allowed"
    ),
    Planted("comma", "operators", lab("return (1, 2);"), "node_type_not_allowed"),
    Planted(
        "try",
        "statements",
        lab("try { return 1; } catch (e) { return 2; }"),
        "node_type_not_allowed",
    ),
    Planted("throw", "statements", lab("throw 1;"), "node_type_not_allowed"),
    Planted(
        "break",
        "statements",
        lab("for (let i = 0; i < 3; i++) { break; } return 1;"),
        "node_type_not_allowed",
    ),
    Planted("empty_statement_call", "statements", lab("p.si; return 1;"), "statement_not_allowed"),
    Planted(
        "const_reassigned",
        "statements",
        lab("const a = 1; a = 2; return a;"),
        "assignment_not_allowed",
    ),
    Planted(
        "declaration_without_value",
        "statements",
        lab("let a; a = 1; return a;"),
        "declaration_not_allowed",
    ),
    # termination and resources
    Planted(
        "while_true",
        "termination",
        lab("let i = 0; while (true) { i += 1; } return 1;"),
        "node_type_not_allowed",
    ),
    Planted(
        "do_while",
        "termination",
        lab("let i = 0; do { i += 1; } while (true); return 1;"),
        "node_type_not_allowed",
    ),
    Planted("for_forever", "termination", lab("for (;;) { } return 1;"), "loop_shape"),
    Planted(
        "for_unbounded_param",
        "termination",
        lab("for (let i = 0; i < p.si; i++) { } return 1;"),
        "loop_shape",
    ),
    Planted(
        "for_huge",
        "termination",
        lab("for (let i = 0; i < 100000000; i++) { } return 1;"),
        "loop_bound",
    ),
    Planted(
        "for_nested_product",
        "termination",
        lab("for (let i = 0; i < 1000; i++) { for (let j = 0; j < 1000; j++) { } } return 1;"),
        "loop_bound",
    ),
    Planted(
        "for_nested_depth",
        "termination",
        lab(
            "for (let i = 0; i < 5; i++) { for (let j = 0; j < 5; j++) { for (let k = 0; k < 5; k++) { } } } return 1;"
        ),
        "loop_bound",
    ),
    Planted(
        "loop_counter_assigned",
        "termination",
        lab("for (let i = 0; i < 3; i++) { i = 0; } return 1;"),
        "assignment_not_allowed",
    ),
    Planted(
        "source_too_large",
        "resources",
        "function lab(p) { return 1; }" + " " * 5000,
        "source_too_large",
    ),
    # floats and totals in the loop budget (found by the red-team review)
    Planted(
        "loop_float_precision",
        "termination",
        lab(
            "let x = 0; for (let i = 10000000000000000; i < 10000000000000010; i++) { x = x + 1; } return x;"
        ),
        "loop_bound",
    ),
    Planted(
        "loop_float_step",
        "termination",
        lab("let x = 0; for (let i = 0; i < 10; i += 0.5) { x = x + 1; } return x;"),
        "loop_bound",
    ),
    Planted(
        "loop_float_bound",
        "termination",
        lab("let x = 0; for (let i = 0; i < 10.5; i++) { x = x + 1; } return x;"),
        "loop_bound",
    ),
    Planted(
        "loop_tiny_step",
        "termination",
        lab("let x = 0; for (let i = 0; i < 10; i += 1e-10) { x = x + 1; } return x;"),
        "loop_bound",
    ),
    Planted(
        "loops_in_sequence_total",
        "termination",
        lab(
            "let x = 0;\n"
            "for (let i = 0; i < 9000; i++) { x = x + 1; }\n"
            "for (let i = 0; i < 9000; i++) { x = x + 1; }\n"
            "for (let i = 0; i < 9000; i++) { x = x + 1; }\n"
            "return x;"
        ),
        "loop_bound",
    ),
    Planted(
        "loop_counter_shadows_math",
        "escape",
        lab("let x = 0; for (let Math = 0; Math < 3; Math++) { x = Math.PI; } return x;"),
        "name_not_allowed",
    ),
    Planted(
        "loop_counter_shadows_p",
        "escape",
        lab("let x = 0; for (let p = 0; p < 3; p++) { x = p.si; } return x;"),
        "name_not_allowed",
    ),
    Planted(
        "loop_counter_denied_name",
        "escape",
        lab(
            "let x = 0; for (let constructor = 0; constructor < 3; constructor++) { x = 1; } return x;"
        ),
        "name_not_allowed",
    ),
    Planted(
        "loop_counter_redeclared",
        "escape",
        lab(
            "let x = 0; for (let i = 0; i < 3; i++) { for (let i = 0; i < 3; i++) { x = 1; } } return x;"
        ),
        "redeclared",
    ),
    Planted("lone_surrogate", "values", lab("return 1;") + chr(0xD800), "source_not_text"),
    # markup and comments (the host places the source inside an inline script element)
    Planted(
        "line_comment", "markup", lab("// harmless?" + chr(10) + "return 1;"), "comment_not_allowed"
    ),
    Planted("block_comment", "markup", lab("/* harmless? */ return 1;"), "comment_not_allowed"),
    Planted(
        "script_close_in_comment",
        "markup",
        lab("// </script><script>alert(1)</script>" + chr(10) + "return 1;"),
        "markup_not_allowed",
    ),
    Planted(
        "html_comment_open", "markup", lab("<!-- x" + chr(10) + "return 1;"), "markup_not_allowed"
    ),
    Planted(
        "html_comment_close", "markup", lab("return 1;" + chr(10) + "--> x"), "markup_not_allowed"
    ),
    # shape
    Planted("two_functions", "shape", GOOD + "\n" + GOOD, "shape"),
    Planted("wrong_name", "shape", "function other(p) { return 1; }", "shape"),
    Planted("wrong_param", "shape", "function lab(q) { return 1; }", "shape"),
    Planted("destructured_param", "shape", "function lab({ si }) { return 1; }", "shape"),
    Planted("async_function", "shape", "async function lab(p) { return 1; }", "shape"),
    Planted("generator_function", "shape", "function* lab(p) { return 1; }", "shape"),
    Planted("top_level_statement", "shape", GOOD + "\nconst x = 1;", "shape"),
    Planted("no_return", "shape", lab("const a = 1;"), "no_return"),
    Planted("syntax_error", "shape", "function lab(p) { return ; ; ;( }", "syntax"),
    Planted("redeclared", "shape", lab("const a = 1; const a = 2; return a;"), "syntax"),
    Planted("empty", "shape", "", "source_empty"),
)
