"""The schema codegen refuses the constructs it used to mishandle silently (found by the P2 A1 spike).

Each test runs the real generator (`packages/schema/codegen/to_python.ts`) on a fixture schema in a temporary
directory through its `--src` and `--out` flags, so nothing in the repo is touched.
"""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

PKG = Path(__file__).resolve().parents[2] / "packages" / "schema"
PNPM = shutil.which("pnpm")

pytestmark = pytest.mark.skipif(PNPM is None, reason="pnpm is not on the path, so the TypeScript generator cannot run")


def generate(tmp_path: Path, source: str, *extra: str) -> subprocess.CompletedProcess[str]:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / "fixture.ts").write_text(source, encoding="utf-8")
    assert PNPM is not None
    return subprocess.run(
        [PNPM, "exec", "tsx", "codegen/to_python.ts", "--src", str(src), "--out", str(tmp_path / "generated.py"), *extra],
        cwd=PKG,
        capture_output=True,
        text=True,
        timeout=120,
    )


def load(tmp_path: Path):
    spec = importlib.util.spec_from_file_location(f"gen_{tmp_path.name}", tmp_path / "generated.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


OWN_LINE = """
export interface Row {
  id: string;
  /** @int */
  count: number;
}
"""
ONE_LINE = "export interface Row { id: string; /** @int */ count: number; }\n"


def test_an_int_tag_on_its_own_line_gives_an_int(tmp_path: Path):
    done = generate(tmp_path, OWN_LINE)
    assert done.returncode == 0, done.stderr
    row = load(tmp_path).Row
    assert row(id="a", count=3).count == 3
    for bad in (3.5, "3", True):
        with pytest.raises(ValidationError):
            row(id="a", count=bad)


def test_an_inline_int_tag_is_refused_instead_of_silently_producing_a_float(tmp_path: Path):
    # Before the guard this generated `count: float` and accepted 3.5 for a field the schema said was an integer.
    done = generate(tmp_path, ONE_LINE)
    assert done.returncode != 0
    assert "`@int` tag is not attached to a property" in done.stderr and "interface Row" in done.stderr
    assert not (tmp_path / "generated.py").exists()


def test_a_number_without_a_tag_is_still_a_float(tmp_path: Path):
    assert generate(tmp_path, "export interface Row { score: number; }\n").returncode == 0
    assert load(tmp_path).Row(score=1.5).score == 1.5


def test_a_discriminated_union_of_five_variants_selects_each_variant(tmp_path: Path):
    variants = "".join(f'export interface V{i} {{ type: "V{i}"; id: string; }}\n' for i in range(5))
    done = generate(tmp_path, variants + "export type Block = V0 | V1 | V2 | V3 | V4;\n")
    assert done.returncode == 0, done.stderr
    module = load(tmp_path)
    adapter = TypeAdapter(module.Block)
    for i in range(5):
        assert type(adapter.validate_python({"type": f"V{i}", "id": "x"})).__name__ == f"V{i}"
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        adapter.validate_python({"type": "V9", "id": "x"})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        adapter.validate_python({"type": "V1", "id": "x", "surprise": 1})


def test_interface_extends_is_refused_because_it_would_drop_the_base_fields(tmp_path: Path):
    done = generate(tmp_path, "export interface Base { a: string; }\nexport interface Sub extends Base { b: string; }\n")
    assert done.returncode != 0
    assert "`extends` is not supported" in done.stderr and "interface Sub" in done.stderr
    assert not (tmp_path / "generated.py").exists()


def test_a_generic_interface_is_refused(tmp_path: Path):
    done = generate(tmp_path, "export interface Box<T> { value: T; }\n")
    assert done.returncode != 0 and "generic interfaces are not supported" in done.stderr


def test_a_generic_type_alias_is_refused(tmp_path: Path):
    done = generate(tmp_path, "export type Maybe<T> = T | null;\n")
    assert done.returncode != 0 and "generic type aliases are not supported" in done.stderr


def test_an_int_tag_that_is_not_attached_to_a_property_is_refused(tmp_path: Path):
    source = "export interface Row {\n  id: string;\n  count: number; /** @int */\n}\n"  # the tag trails the property
    done = generate(tmp_path, source)
    assert done.returncode != 0 and "`@int` tag is not attached to a property" in done.stderr


def test_a_union_variant_without_a_literal_type_is_still_refused(tmp_path: Path):
    source = 'export interface NoTag { x: string; }\nexport interface Tagged { type: "Tagged"; }\nexport type U = NoTag | Tagged;\n'
    done = generate(tmp_path, source)
    assert done.returncode != 0 and "needs a string-literal `type` property" in done.stderr


@pytest.mark.parametrize("construct", ["pair: [string, number];", "both: string & { b: number };", "data: { x: string };"])
def test_unsupported_field_types_still_fail_loudly(tmp_path: Path, construct: str):
    done = generate(tmp_path, f"export interface Bad {{ {construct} }}\n")
    assert done.returncode != 0 and "unsupported construct" in done.stderr


def test_check_mode_reports_drift_on_a_changed_schema(tmp_path: Path):
    assert generate(tmp_path, "export interface Row { id: string; }\n").returncode == 0
    assert generate(tmp_path, "export interface Row { id: string; }\n", "--check").returncode == 0
    drifted = generate(tmp_path, "export interface Row { id: string; extra: string; }\n", "--check")
    assert drifted.returncode != 0 and "out of sync" in drifted.stderr
