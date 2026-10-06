// Ported from Azimlearning/Arcana (v1), packages/schema/codegen/to_python.ts @ 9a3d67f.
// Read in full and adapted for v2 (D-01, D-16). Changes from v1:
//   - emits api/genui/generated.py (not _generated.py);
//   - every model forbids unknown fields (extra='forbid'), so a stray key fails validation;
//   - `/** @int */` on a property maps its `number` to Python `int`;
//   - `--check` compares with line endings normalised, so a CRLF checkout is not false drift.
//
// Walks packages/schema/src/*.ts and emits Pydantic models. The generated file is committed;
// `codegen:check` regenerates in memory and exits non-zero if the committed file differs.
//
// Supported TS constructs (extend as the schema grows; anything else fails loudly):
//   - export interface Foo { ... }          -> class Foo(BaseModel)
//   - export type X = 'a' | 'b'             -> X = Literal['a', 'b']
//   - export type X = Y                     -> X = Y
//   - export type X = A | B (class refs)    -> X = Annotated[A | B, Field(discriminator='type')]
//   - field types: string | number | boolean | null | unknown | T[] | Array<T>
//                  | Record<K, V> | 'literal' | Foo | A | B | null

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Project, SyntaxKind } from "ts-morph";
import type {
  InterfaceDeclaration,
  PropertySignature,
  TypeAliasDeclaration,
  TypeNode,
  UnionTypeNode,
} from "ts-morph";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG_ROOT = resolve(__dirname, "..");
const REPO_ROOT = resolve(PKG_ROOT, "..", "..");
// `--src <dir>` and `--out <file>` exist so the guards below can be tested on fixture schemas without touching the
// repo (api/genui/test_codegen_guard.py). With neither flag the behaviour is exactly as before.
function argValue(flag: string): string | undefined {
  const i = process.argv.indexOf(flag);
  return i >= 0 ? process.argv[i + 1] : undefined;
}
const srcArg = argValue("--src");
const outArg = argValue("--out");
const OUTPUT = outArg ? resolve(outArg) : resolve(REPO_ROOT, "api", "genui", "generated.py");

const isCheck = process.argv.includes("--check");

const project = srcArg
  ? new Project({ skipAddingFilesFromTsConfig: true })
  : new Project({
      tsConfigFilePath: resolve(PKG_ROOT, "tsconfig.json"),
      skipAddingFilesFromTsConfig: false,
    });
if (srcArg) project.addSourceFilesAtPaths(resolve(srcArg).replace(/\\/g, "/") + "/**/*.ts");

interface IfaceItem {
  kind: "iface";
  name: string;
  node: InterfaceDeclaration;
}
interface AliasItem {
  kind: "alias";
  name: string;
  node: TypeAliasDeclaration;
}
type Item = IfaceItem | AliasItem;

const items: Item[] = [];
// ts-morph returns POSIX-style paths even on Windows; normalise for the prefix check.
const SRC_DIR = (srcArg ? resolve(srcArg) : resolve(PKG_ROOT, "src")).replace(/\\/g, "/");
for (const sf of project.getSourceFiles()) {
  const fp = sf.getFilePath().replace(/\\/g, "/");
  if (!fp.startsWith(SRC_DIR)) continue;
  for (const iface of sf.getInterfaces()) {
    if (iface.isExported()) items.push({ kind: "iface", name: iface.getName(), node: iface });
  }
  for (const alias of sf.getTypeAliases()) {
    if (alias.isExported()) items.push({ kind: "alias", name: alias.getName(), node: alias });
  }
}

if (items.length === 0) {
  process.stderr.write("codegen: no exported interfaces or type aliases found under src/.\n");
  process.exit(1);
}

// ─── Type mapping ─────────────────────────────────────────────
function fail(ctx: string, detail: string): never {
  process.stderr.write(`codegen: unsupported construct at ${ctx}: ${detail}\n`);
  process.exit(1);
}

function isStringLiteralText(t: string): boolean {
  return /^(['"]).*\1$/.test(t);
}

function normalizeStringLiteral(t: string): string {
  return `'${t.slice(1, -1)}'`;
}

function mapPrimitive(text: string, ctx: string): string {
  switch (text) {
    case "string":
      return "str";
    case "number":
      return "float";
    case "boolean":
      return "bool";
    case "null":
      return "None";
    case "unknown":
      return "Any";
  }
  if (isStringLiteralText(text)) return `Literal[${normalizeStringLiteral(text)}]`;
  // Bare identifier: a declared interface or alias (forward refs are fine under __future__ annotations).
  if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(text)) return text;
  return fail(ctx, `cannot map type "${text}"`);
}

function mapTypeNode(node: TypeNode, ctx: string): string {
  const kind = node.getKind();
  if (kind === SyntaxKind.ArrayType) {
    const elem = node.asKindOrThrow(SyntaxKind.ArrayType).getElementTypeNode();
    return `list[${mapTypeNode(elem, ctx)}]`;
  }
  if (kind === SyntaxKind.TypeReference) {
    const ref = node.asKindOrThrow(SyntaxKind.TypeReference);
    const name = ref.getTypeName().getText();
    const args = ref.getTypeArguments();
    if (name === "Array") {
      const a = args[0];
      if (args.length !== 1 || !a) fail(ctx, "Array<...> needs exactly 1 type arg");
      return `list[${mapTypeNode(a as TypeNode, ctx)}]`;
    }
    if (name === "Record") {
      const k = args[0];
      const v = args[1];
      if (args.length !== 2 || !k || !v) fail(ctx, "Record<...> needs exactly 2 type args");
      return `dict[${mapTypeNode(k as TypeNode, ctx)}, ${mapTypeNode(v as TypeNode, ctx)}]`;
    }
    return mapPrimitive(name, ctx);
  }
  if (kind === SyntaxKind.UnionType) {
    return mapUnionTypeNode(node.asKindOrThrow(SyntaxKind.UnionType), ctx);
  }
  if (kind === SyntaxKind.LiteralType) {
    const text = node.getText();
    if (text === "null") return "None";
    if (isStringLiteralText(text)) return `Literal[${normalizeStringLiteral(text)}]`;
    fail(ctx, `unsupported literal "${text}"`);
  }
  return mapPrimitive(node.getText(), ctx);
}

function mapUnionTypeNode(union: UnionTypeNode, ctx: string): string {
  const parts = union.getTypeNodes();
  const nonNull = parts.filter((p) => p.getText() !== "null");
  const hasNull = nonNull.length !== parts.length;

  if (nonNull.length > 0 && nonNull.every((p) => isStringLiteralText(p.getText()))) {
    const lits = nonNull.map((p) => normalizeStringLiteral(p.getText())).join(", ");
    const py = `Literal[${lits}]`;
    return hasNull ? `${py} | None` : py;
  }

  const mapped = nonNull.map((p) => mapTypeNode(p, ctx));
  if (mapped.length === 0) fail(ctx, "empty union");
  const py = mapped.join(" | ");
  return hasNull ? `${py} | None` : py;
}

// ─── Emitters ─────────────────────────────────────────────────
function hasIntTag(prop: PropertySignature): boolean {
  // Only a JSDoc comment attached to the property counts. A one-line `{ id: string; /** @int */ page: number }` is
  // parsed as a trailing comment of the previous property, so the tag is not attached; emitInterface refuses it
  // (it used to be ignored silently and the field became `float`).
  return prop
    .getJsDocs()
    .some((doc) => doc.getTags().some((tag) => tag.getTagName() === "int"));
}

function emitInterface(iface: InterfaceDeclaration): string {
  const name = iface.getName();
  const ctx = `interface ${name}`;
  // Three constructs the generator used to accept and mishandle silently (found by the P2 A1 spike). Each now stops
  // the build: they weaken validation or break the generated module instead of failing where the schema is written.
  if (iface.getExtends().length > 0) {
    fail(ctx, "`extends` is not supported: the base interface's fields would be silently dropped from the model");
  }
  if (iface.getTypeParameters().length > 0) {
    fail(ctx, "generic interfaces are not supported: the generated Python module could not be imported");
  }
  const intMentions = (iface.getText().match(/@int\b/g) ?? []).length;
  const intTagged = iface.getProperties().filter(hasIntTag).length;
  if (intMentions !== intTagged) {
    fail(ctx, "an `@int` tag is not attached to a property (put `/** @int */` directly before the property it applies to)");
  }
  // strict: no coercion ("1" or true is not an int); extra='forbid': unknown keys fail. Both fail closed.
  const lines: string[] = [
    `class ${name}(BaseModel):`,
    "    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)",
  ];
  for (const prop of iface.getProperties()) {
    const propName = prop.getName();
    const typeNode = prop.getTypeNode();
    if (!typeNode) fail(`${ctx}.${propName}`, "missing type annotation");
    let py = mapTypeNode(typeNode as TypeNode, `${ctx}.${propName}`);
    if (hasIntTag(prop)) py = py.replace(/\bfloat\b/g, "int");
    const optional = prop.hasQuestionToken();
    if (optional && !py.endsWith(" | None")) py = `${py} | None`;
    lines.push(`    ${propName}: ${py}${optional ? " = None" : ""}`);
  }
  return lines.join("\n");
}

function hasTypeLiteral(interfaceName: string): boolean {
  const item = items.find((i) => i.kind === "iface" && i.name === interfaceName);
  if (!item || item.kind !== "iface") return false;
  const typeProp = item.node.getProperty("type");
  const typeNode = typeProp?.getTypeNode();
  return typeNode !== undefined && isStringLiteralText(typeNode.getText());
}

function emitAlias(alias: TypeAliasDeclaration): string {
  const name = alias.getName();
  const ctx = `type ${name}`;
  if (alias.getTypeParameters().length > 0) {
    fail(ctx, "generic type aliases are not supported: the generated Python module could not be imported");
  }
  const typeNode = alias.getTypeNode();
  if (!typeNode) fail(ctx, "missing body");
  const node = typeNode as TypeNode;

  if (node.getKind() === SyntaxKind.UnionType) {
    const union = node.asKindOrThrow(SyntaxKind.UnionType);
    const parts = union.getTypeNodes();
    const allRefs = parts.every((p) => /^[A-Z][A-Za-z0-9_]*$/.test(p.getText()));
    if (allRefs && parts.length > 1) {
      for (const p of parts) {
        if (!hasTypeLiteral(p.getText())) {
          fail(ctx, `union variant ${p.getText()} needs a string-literal \`type\` property to be a discriminated union`);
        }
      }
      return `${name} = Annotated[${parts.map((p) => p.getText()).join(" | ")}, Field(discriminator='type')]`;
    }
    return `${name} = ${mapUnionTypeNode(union, ctx)}`;
  }
  if (node.getKind() === SyntaxKind.TypeReference) return `${name} = ${node.getText()}`;
  return `${name} = ${mapTypeNode(node, ctx)}`;
}

// ─── Output: interfaces first (sorted), then aliases (sorted) ──
// Module-level alias bindings are evaluated immediately, so the classes they reference come first.
const interfaces = items.filter((i): i is IfaceItem => i.kind === "iface");
const aliases = items.filter((i): i is AliasItem => i.kind === "alias");
// Plain comparison, not localeCompare: output must be identical on every machine and CI image.
const byName = (a: { name: string }, b: { name: string }) =>
  a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
interfaces.sort(byName);
aliases.sort(byName);

const body: string[] = [];
for (const item of interfaces) body.push(emitInterface(item.node), "", "");
for (const item of aliases) body.push(emitAlias(item.node), "");
// Classes reference later-defined names (annotations are strings); resolve them now, not lazily.
for (const item of interfaces) body.push(`${item.name}.model_rebuild()`);

// Import only what the body uses, so the generated file is lint-clean.
const bodyJoined = body.join("\n");
const typingNames: string[] = [];
if (bodyJoined.includes("Annotated[")) typingNames.push("Annotated");
if (/\bAny\b/.test(bodyJoined)) typingNames.push("Any");
if (bodyJoined.includes("Literal[")) typingNames.push("Literal");
const pydanticNames = ["BaseModel", "ConfigDict"];
if (bodyJoined.includes("Field(")) pydanticNames.push("Field");

const header: string[] = [
  "# DO NOT EDIT: generated by packages/schema/codegen/to_python.ts.",
  "# Regenerate with: pnpm codegen",
  "# Drift is caught by: pnpm codegen:check",
  "#",
  "# Source: packages/schema/src/*.ts. These models are the server side of the wire contract:",
  "# every block is re-validated against them before it is streamed (fail closed).",
  "",
  "from __future__ import annotations",
  "",
];
if (typingNames.length > 0) header.push(`from typing import ${typingNames.join(", ")}`, "");
header.push(`from pydantic import ${pydanticNames.join(", ")}`, "", "");

let content = [...header, ...body].join("\n");
content = content.replace(/\n{4,}/g, "\n\n\n");
if (!content.endsWith("\n")) content += "\n";

// ─── Write or check ───────────────────────────────────────────
const normalise = (s: string) => s.replace(/\r\n/g, "\n");

if (isCheck) {
  if (!existsSync(OUTPUT)) {
    process.stderr.write(`codegen:check FAILED: ${OUTPUT} does not exist.\nRun: pnpm codegen\n`);
    process.exit(1);
  }
  if (normalise(readFileSync(OUTPUT, "utf-8")) !== normalise(content)) {
    process.stderr.write(
      `codegen:check FAILED: ${OUTPUT} is out of sync with packages/schema/src/.\nRun: pnpm codegen\n`,
    );
    process.exit(1);
  }
  process.stdout.write("codegen:check OK\n");
} else {
  mkdirSync(dirname(OUTPUT), { recursive: true });
  writeFileSync(OUTPUT, content, "utf-8");
  process.stdout.write(`codegen: wrote ${OUTPUT}\n`);
}
