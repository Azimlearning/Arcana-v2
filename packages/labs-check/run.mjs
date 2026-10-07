// The VerifiedLab runner (P4 V3, D-36): runs one already-checked generated function on many parameter vectors and prints the numbers.
//
//   echo '{"source": "...", "vectors": [{"si": 0, "sj": 1}, ...], "timeoutMs": 500}' | node --max-old-space-size=64 run.mjs
//
// IMPORTANT: `node:vm` is NOT a security mechanism (the Node documentation says: "Do not use it to run untrusted code"). It is used
// here as a correctness and resource harness: a fresh context with a null-prototype global, code generation from strings and WebAssembly
// switched off, a per-call wall-clock limit, and the whole process under a memory limit and a time limit set by the parent
// (api/labs/verifier.py). Isolation rests on the process boundary on the server and on the sandboxed iframe in the browser; the checker
// (check.mjs) has already refused every construct that could reach anything but numbers.

import { readFileSync } from "node:fs";
import vm from "node:vm";
import { performance } from "node:perf_hooks";

const MAX_VECTORS = 5000;
const input = JSON.parse(readFileSync(0, "utf8"));
const { source, vectors } = input;
const timeoutMs = Math.min(Math.max(Number(input.timeoutMs) || 200, 10), 2000);

function fail(code, message) {
  process.stdout.write(JSON.stringify({ ok: false, code, message }));
  process.exit(0);
}

if (typeof source !== "string" || !Array.isArray(vectors) || vectors.length === 0 || vectors.length > MAX_VECTORS) {
  fail("bad_input", "the runner needs a source and between 1 and 5000 parameter vectors");
}

const context = vm.createContext(Object.create(null), {
  name: "lab",
  codeGeneration: { strings: false, wasm: false },
});

try {
  new vm.Script(`"use strict";\n${source}\n;globalThis.__lab = lab;`, { filename: "lab.js" }).runInContext(context, { timeout: timeoutMs });
} catch (error) {
  fail("load_failed", String(error?.message ?? error).slice(0, 200));
}

const call = new vm.Script("__out = __lab(__p)", { filename: "call.js" });
const values = [];
let slowest = 0;
for (const vector of vectors) {
  const p = Object.freeze(Object.assign(Object.create(null), vector));
  context.__p = p;
  const began = performance.now();
  try {
    call.runInContext(context, { timeout: timeoutMs });
    slowest = Math.max(slowest, performance.now() - began);
  } catch (error) {
    const message = String(error?.message ?? error).slice(0, 200);
    fail(/timed out/i.test(message) ? "timeout" : "threw", message);
  }
  const out = context.__out;
  if (typeof out !== "number") fail("not_a_number", `the function returned a ${typeof out}`);
  values.push(Number.isFinite(out) ? out : String(out)); // "NaN", "Infinity", "-Infinity" stay visible to the verifier
}
process.stdout.write(JSON.stringify({ ok: true, values, slowestCallMs: slowest }));
