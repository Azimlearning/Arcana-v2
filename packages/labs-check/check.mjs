// The VerifiedLab checker (P4 V2, D-36): static analysis of one generated function by an AST allowlist.
//
//   node check.mjs --params si,sj  < source.js      prints {"ok": bool, "problems": [{rule, message, line, column}]}
//
// The accepted language is deliberately tiny: ONE function `function lab(p) { ... }` over numbers. Its only values are numbers and
// booleans; the only names it may use are its own locals, `p.<declared parameter>` and `Math.<listed function or constant>`. There are
// no strings, arrays, objects, closures, calls other than `Math.<listed>(...)`, no `new`, `this`, `try`, `while`, labels, classes,
// regular expressions or template literals, and loops are `for (let i = <number>; i < <number>; i++)` with a literal bound. Because no
// value but a number can exist, there is nothing to reach a prototype, a global or a constructor from: the checker is an allowlist
// that fails closed, and the isolated runner (run.mjs) is a second, independent line.
//
// Rules are named so the mutation suite can say which rule must reject which planted defect.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import * as acorn from "acorn";

const here = dirname(fileURLToPath(import.meta.url));
export const ALLOWLIST = JSON.parse(readFileSync(join(here, "allowlist.json"), "utf8"));

const MATH_FUNCTIONS = new Set(ALLOWLIST.math_functions);
const MATH_CONSTANTS = new Set(ALLOWLIST.math_constants);
const BINARY = new Set(ALLOWLIST.binary_operators);
const LOGICAL = new Set(ALLOWLIST.logical_operators);
const UNARY = new Set(ALLOWLIST.unary_operators);
const ASSIGN = new Set(ALLOWLIST.assignment_operators);
const UPDATE = new Set(ALLOWLIST.update_operators);
const DENIED_NAMES = new Set(ALLOWLIST.denied_local_names);
const LOCAL_NAME = /^[a-z][a-zA-Z0-9_]{0,20}$/;

/** Check `source` against the allowlist. `paramNames` are the contract's declared parameters. Returns the problems found. */
export function check(source, paramNames) {
  const problems = [];
  const fail = (rule, node, message) => {
    problems.push({ rule, message, line: node?.loc?.start.line ?? 0, column: node?.loc?.start.column ?? 0 });
  };

  if (typeof source !== "string" || source.length === 0) {
    fail("source_empty", null, "the source is empty");
    return problems;
  }
  if (source.length > ALLOWLIST.max_source_chars) {
    fail("source_too_large", null, `the source is longer than ${ALLOWLIST.max_source_chars} characters`);
    return problems;
  }
  let ast;
  try {
    ast = acorn.parse(source, { ecmaVersion: 2022, sourceType: "script", locations: true });
  } catch (error) {
    fail("syntax", { loc: { start: { line: error.loc?.line ?? 0, column: error.loc?.column ?? 0 } } }, String(error.message));
    return problems;
  }

  // Shape: exactly `function lab(p) { ... }`.
  if (ast.body.length !== 1 || ast.body[0].type !== "FunctionDeclaration") {
    fail("shape", ast, "the source must be exactly one function declaration");
    return problems;
  }
  const fn = ast.body[0];
  if (fn.id?.name !== ALLOWLIST.function_name || fn.params.length !== 1 || fn.params[0].type !== "Identifier" || fn.params[0].name !== ALLOWLIST.param_name) {
    fail("shape", fn, `the function must be \`function ${ALLOWLIST.function_name}(${ALLOWLIST.param_name})\``);
    return problems;
  }
  if (fn.async || fn.generator) {
    fail("shape", fn, "the function must be neither async nor a generator");
    return problems;
  }

  const params = new Set(paramNames);
  let nodes = 0;
  const scopes = [new Map()]; // name -> {kind: "let" | "const" | "loop"}
  const find = (name) => {
    for (let i = scopes.length - 1; i >= 0; i--) if (scopes[i].has(name)) return scopes[i].get(name);
    return null;
  };
  const declare = (id, kind, node) => {
    if (id.type !== "Identifier") return fail("pattern", node, "only plain names may be declared");
    if (!LOCAL_NAME.test(id.name) || DENIED_NAMES.has(id.name)) return fail("name_not_allowed", id, `the name ${id.name} is not allowed`);
    if (find(id.name)) return fail("redeclared", id, `${id.name} is already declared`);
    scopes[scopes.length - 1].set(id.name, { kind });
  };

  const countNode = (node) => {
    nodes += 1;
    if (nodes === ALLOWLIST.max_nodes + 1) fail("source_too_large", node, `more than ${ALLOWLIST.max_nodes} syntax nodes`);
  };

  const numberLiteral = (node) => node.type === "Literal" && typeof node.value === "number" && Number.isFinite(node.value);

  function expression(node) {
    countNode(node);
    switch (node.type) {
      case "Literal":
        if (typeof node.value === "number" && Number.isFinite(node.value)) return;
        if (typeof node.value === "boolean") return;
        return fail("literal_not_allowed", node, "only finite numbers and booleans are literals");
      case "Identifier": {
        if (node.name === ALLOWLIST.param_name || node.name === "Math") return fail("identifier_not_allowed", node, `${node.name} may only be used as ${node.name}.<name>`);
        if (!find(node.name)) return fail("identifier_not_allowed", node, `${node.name} is not a declared local`);
        return;
      }
      case "MemberExpression":
        return member(node, false);
      case "CallExpression": {
        const callee = node.callee;
        if (callee.type !== "MemberExpression" || callee.computed || callee.object.type !== "Identifier" || callee.object.name !== "Math" || callee.property.type !== "Identifier" || !MATH_FUNCTIONS.has(callee.property.name)) {
          return fail("call_not_allowed", node, "the only calls are Math.<listed function>(...)");
        }
        countNode(callee);
        if (node.arguments.length > ALLOWLIST.max_call_args) return fail("call_not_allowed", node, "too many arguments");
        for (const arg of node.arguments) {
          if (arg.type === "SpreadElement") return fail("node_type_not_allowed", arg, "spread is not allowed");
          expression(arg);
        }
        return;
      }
      case "BinaryExpression":
        if (!BINARY.has(node.operator)) return fail("operator_not_allowed", node, `the operator ${node.operator} is not allowed`);
        if (node.left.type === "PrivateIdentifier") return fail("node_type_not_allowed", node, "private names are not allowed");
        expression(node.left);
        return expression(node.right);
      case "LogicalExpression":
        if (!LOGICAL.has(node.operator)) return fail("operator_not_allowed", node, `the operator ${node.operator} is not allowed`);
        expression(node.left);
        return expression(node.right);
      case "UnaryExpression":
        if (!UNARY.has(node.operator)) return fail("operator_not_allowed", node, `the operator ${node.operator} is not allowed`);
        return expression(node.argument);
      case "ConditionalExpression":
        expression(node.test);
        expression(node.consequent);
        return expression(node.alternate);
      default:
        return fail("node_type_not_allowed", node, `${node.type} is not allowed in an expression`);
    }
  }

  /** `p.<declared parameter>` or `Math.<constant>` as a value (a Math function is only ever a callee). */
  function member(node, asCallee) {
    countNode(node);
    if (node.computed) return fail("member_not_allowed", node, "computed property access is not allowed");
    if (node.object.type !== "Identifier" || node.property.type !== "Identifier") return fail("member_not_allowed", node, "only p.<parameter> and Math.<constant> are allowed");
    const obj = node.object.name;
    const prop = node.property.name;
    if (obj === ALLOWLIST.param_name) {
      if (!params.has(prop)) return fail("member_not_allowed", node, `p.${prop} is not a declared parameter`);
      return;
    }
    if (obj === "Math" && !asCallee) {
      if (!MATH_CONSTANTS.has(prop)) return fail("member_not_allowed", node, `Math.${prop} is not a listed constant`);
      return;
    }
    return fail("member_not_allowed", node, "only p.<parameter> and Math.<constant> are allowed");
  }

  let loopDepth = 0;
  let loopProduct = 1;

  function assignTarget(left, node) {
    if (left.type !== "Identifier") return fail("assignment_not_allowed", node, "only a local name can be assigned to");
    const binding = find(left.name);
    if (!binding) return fail("assignment_not_allowed", left, `${left.name} is not a declared local`);
    if (binding.kind !== "let") return fail("assignment_not_allowed", left, `${left.name} cannot be assigned to (a constant or a loop counter)`);
  }

  function statement(node) {
    countNode(node);
    switch (node.type) {
      case "VariableDeclaration":
        if (node.kind !== "let" && node.kind !== "const") return fail("node_type_not_allowed", node, "only let and const");
        for (const d of node.declarations) {
          countNode(d);
          if (!d.init) return fail("declaration_not_allowed", d, "a declaration needs a value");
          expression(d.init); // the initialiser is checked before the name exists
          declare(d.id, node.kind, d);
        }
        return;
      case "ReturnStatement":
        if (!node.argument) return fail("return_not_allowed", node, "return needs a value");
        return expression(node.argument);
      case "IfStatement":
        expression(node.test);
        body(node.consequent);
        if (node.alternate) body(node.alternate);
        return;
      case "ExpressionStatement": {
        const e = node.expression;
        countNode(e);
        if (e.type === "AssignmentExpression") {
          if (!ASSIGN.has(e.operator)) return fail("operator_not_allowed", e, `the operator ${e.operator} is not allowed`);
          assignTarget(e.left, e);
          return expression(e.right);
        }
        if (e.type === "UpdateExpression") {
          if (!UPDATE.has(e.operator)) return fail("operator_not_allowed", e, `the operator ${e.operator} is not allowed`);
          return assignTarget(e.argument, e);
        }
        return fail("statement_not_allowed", node, "an expression statement must be an assignment or an update");
      }
      case "ForStatement":
        return forLoop(node);
      case "BlockStatement":
        return block(node);
      default:
        return fail("node_type_not_allowed", node, `${node.type} is not allowed`);
    }
  }

  function body(node) {
    if (node.type === "BlockStatement") return block(node);
    scopes.push(new Map());
    statement(node);
    scopes.pop();
  }

  function block(node) {
    countNode(node);
    scopes.push(new Map());
    for (const s of node.body) statement(s);
    scopes.pop();
  }

  function forLoop(node) {
    const init = node.init;
    const test = node.test;
    const update = node.update;
    if (!init || init.type !== "VariableDeclaration" || init.kind !== "let" || init.declarations.length !== 1 || !init.declarations[0].init || !numberLiteral(init.declarations[0].init) || init.declarations[0].id.type !== "Identifier") {
      return fail("loop_shape", node, "a loop starts with `let i = <number>`");
    }
    const name = init.declarations[0].id.name;
    const start = init.declarations[0].init.value;
    if (!test || test.type !== "BinaryExpression" || (test.operator !== "<" && test.operator !== "<=") || test.left.type !== "Identifier" || test.left.name !== name || !numberLiteral(test.right)) {
      return fail("loop_shape", node, "a loop tests `i < <number>` or `i <= <number>`");
    }
    let step = null;
    if (update?.type === "UpdateExpression" && update.operator === "++" && update.argument.type === "Identifier" && update.argument.name === name) step = 1;
    else if (update?.type === "AssignmentExpression" && update.operator === "+=" && update.left.type === "Identifier" && update.left.name === name && numberLiteral(update.right) && update.right.value > 0) step = update.right.value;
    if (step === null) return fail("loop_shape", node, "a loop steps with `i++` or `i += <positive number>`");
    const bound = test.operator === "<" ? test.right.value : test.right.value + step;
    const iterations = Math.max(0, Math.ceil((bound - start) / step));
    if (!Number.isFinite(iterations) || iterations > ALLOWLIST.max_loop_bound) return fail("loop_bound", node, `a loop runs at most ${ALLOWLIST.max_loop_bound} times`);
    loopDepth += 1;
    loopProduct *= Math.max(iterations, 1);
    if (loopDepth > ALLOWLIST.max_loop_depth) fail("loop_bound", node, `loops nest at most ${ALLOWLIST.max_loop_depth} deep`);
    if (loopProduct > ALLOWLIST.max_loop_product) fail("loop_bound", node, `nested loops run at most ${ALLOWLIST.max_loop_product} times in all`);
    countNode(init);
    scopes.push(new Map([[name, { kind: "loop" }]]));
    if (node.body.type !== "BlockStatement") fail("loop_shape", node.body, "a loop body is a block");
    else block(node.body);
    scopes.pop();
    loopDepth -= 1;
    loopProduct /= Math.max(iterations, 1);
  }

  for (const s of fn.body.body) statement(s);
  if (!fn.body.body.some((s) => s.type === "ReturnStatement")) fail("no_return", fn, "the function never returns a value at its top level");
  return problems;
}

// CLI: read the source from stdin, print the verdict as JSON.
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const index = process.argv.indexOf("--params");
  const names = index >= 0 ? (process.argv[index + 1] ?? "").split(",").filter(Boolean) : [];
  const source = readFileSync(0, "utf8");
  const problems = check(source, names);
  process.stdout.write(JSON.stringify({ ok: problems.length === 0, problems }));
}
