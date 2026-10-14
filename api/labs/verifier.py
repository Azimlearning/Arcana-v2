"""The lab verifier and the mint (P4 V3, D-36): the only code that can create a `VerifiedArtifact`.

`verify(contract, source)` runs, in order: the checker (the AST allowlist), then the isolated runner on **every value the interface can ask for**
and a seeded fuzz, then the contract's properties and its Python reference function. Only if every stage passes does it construct a
`VerifiedArtifact`. Any failure is a `VerificationFailed` naming the stage and the reason; the source is never trusted and never evaluated in
this process (the runner is a Node child process).

**Why every grid point.** A sample can never be complete: a function that matches the reference on a few hundred inputs can still hide a branch
at one other input (a red-team review made exactly that: a source verified in 0.3 s that froze the iframe at one slider position). So the
contract fixes a grid (each parameter takes `grid + 1` evenly spaced values, the sliders snap to it, the swept axis uses it) and the verifier
runs **all combinations** of it, bounded by `MAX_GRID_VECTORS`. The values the interface can request are then exactly the values that were
verified. The seeded fuzz is kept as extra evidence about the continuous range, not as the guarantee.

`VerifiedArtifact` is the type the delivery path accepts (hard constraint 3). It is created through a function that holds the mint token in a
closure (not a module attribute), cannot be subclassed, changed or copied. That is hardening, not a language guarantee: Python cannot stop
code in the same process from forging an object, and this process never runs generated code. The lines downstream do not rely on it: the store
ties the id to the hash, and the delivery gate re-hashes and re-checks the stored source (see `api/genui/validate.py`).
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
from dataclasses import dataclass
from itertools import product
from typing import TYPE_CHECKING, Any

from api.labs.checker import TOOL_DIR, LabToolError, check_source, node_path
from api.labs.contract import REFERENCES, LabContract, LabParameter

TEMPLATE_VERSION = 2
"""The version of the fixed template the web host holds (`web/lib/labFrame.ts`, V6). A block built for another version is refused."""
FUZZ_SEED = 20261008
FUZZ_CASES = 200
RUN_TIMEOUT_SECONDS = 30
PER_CALL_TIMEOUT_MS = 500
MAX_MEAN_CALL_MS = 5.0
"""The mean call time allowed: the host calls the function once per sweep point (up to 101 times) on every slider move, so the mean is what a slider
move costs, and a function over this makes the page janky. The mean, not the slowest call, because one scheduling hiccup on a busy machine must not
refuse a good lab (a wall-clock maximum did exactly that under load)."""
MAX_CALL_MS = 250.0
"""...and no single call may take longer than this (a pathological function; the runner's own limit is `PER_CALL_TIMEOUT_MS`)."""
CHUNK_VECTORS = 4000
MAX_RUNNER_MEMORY_MB = 64
EPS = 1e-12


class VerificationFailed(Exception):
    """A lab did not pass: `stage` names where, `reason` says why."""

    def __init__(self, stage: str, reason: str):
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason


class MintRefused(RuntimeError):
    """A `VerifiedArtifact` was asked for without going through the verifier."""


@dataclass(frozen=True)
class Checked:
    reference_cases: int
    properties: int
    fuzz_cases: int
    grid_points: int


_FIELDS = (
    "lab_id",
    "contract_id",
    "contract_sha256",
    "title",
    "parameters",
    "source",
    "source_sha256",
    "template_version",
    "checked",
)


def _make_artifact_class() -> tuple[type, Any]:
    token = object()  # held here, in a closure: no module attribute carries it

    class VerifiedArtifact:
        """What the verifier mints: a lab function that passed every stage, with its hash and the counts of what was checked."""

        __slots__ = (*_FIELDS, "_frozen")

        def __init_subclass__(cls, **kwargs: Any) -> None:
            raise TypeError("a VerifiedArtifact cannot be subclassed")

        def __init__(self, *, _mint: object = None, **fields: Any):
            if _mint is not token:
                raise MintRefused("a VerifiedArtifact can only be created by the verifier")
            if set(fields) != set(_FIELDS):
                raise MintRefused("a VerifiedArtifact needs exactly its fields")
            for name, value in fields.items():
                object.__setattr__(self, name, value)
            object.__setattr__(self, "_frozen", True)

        def __setattr__(self, name: str, value: Any) -> None:
            raise AttributeError("a VerifiedArtifact cannot be changed")

        def __delattr__(self, name: str) -> None:
            raise AttributeError("a VerifiedArtifact cannot be changed")

        def __repr__(self) -> str:
            return f"VerifiedArtifact({self.lab_id})"  # type: ignore[attr-defined]

    def issue(**fields: Any) -> Any:
        return VerifiedArtifact(_mint=token, **fields)

    return VerifiedArtifact, issue


_artifact_class, _issue = _make_artifact_class()
if TYPE_CHECKING:  # the static view of the class the factory makes

    class VerifiedArtifact:
        lab_id: str
        contract_id: str
        contract_sha256: str
        title: str
        parameters: tuple[LabParameter, ...]
        source: str
        source_sha256: str
        template_version: int
        checked: Checked

        def __init__(self, **fields: Any) -> None: ...

else:
    VerifiedArtifact = _artifact_class
"""The class (public: it is the type the delivery path accepts) and the one function that creates one (`_issue`, private to this module; a test
scans the repository for any other use of it)."""


def source_sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def contract_sha256(contract: LabContract) -> str:
    """A fingerprint of everything a contract promises. A lab verified for one contract is not delivered under a changed one."""
    return hashlib.sha256(contract.model_dump_json().encode("utf-8")).hexdigest()


def lab_id_for(contract_id: str, sha: str) -> str:
    return f"{contract_id}-{sha[:12]}"


# ── the battery of parameter vectors ───────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Battery:
    vectors: list[dict[str, float]]
    cases: slice
    grid: slice
    strides: dict[str, int]
    """For each parameter, how far apart in the grid block two vectors are that differ only in that parameter by one step."""
    extra: slice


def _battery(contract: LabContract) -> _Battery:
    names = [p.name for p in contract.parameters]
    levels = [contract.grid_values(n) for n in names]
    vectors: list[dict[str, float]] = [dict(case.params) for case in contract.cases]
    cases = slice(0, len(vectors))
    start = len(vectors)
    for combo in product(*levels):  # the last parameter varies fastest
        vectors.append(dict(zip(names, combo, strict=True)))
    grid = slice(start, len(vectors))
    size = contract.grid + 1
    strides = {n: size ** (len(names) - 1 - i) for i, n in enumerate(names)}
    extra_start = len(vectors)
    rng = random.Random(FUZZ_SEED)
    for _ in range(FUZZ_CASES):
        vectors.append({p.name: rng.uniform(p.min, p.max) for p in contract.parameters})
    return _Battery(vectors, cases, grid, strides, slice(extra_start, len(vectors)))


# ── running ─────────────────────────────────────────────────────────────────────────────────────────────────────────────


def _run_chunk(source: str, vectors: list[dict[str, float]]) -> tuple[list[float | str], float, float]:
    script = TOOL_DIR / "run.mjs"
    if not script.exists():
        raise LabToolError("the lab runner is missing")
    payload = json.dumps(
        {"source": source, "vectors": vectors, "timeoutMs": PER_CALL_TIMEOUT_MS}
    ).encode("utf-8")
    try:
        done = subprocess.run(
            [node_path(), f"--max-old-space-size={MAX_RUNNER_MEMORY_MB}", str(script)],
            input=payload,
            capture_output=True,
            timeout=RUN_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise VerificationFailed("run", "the function did not finish in time") from exc
    if done.returncode != 0:
        raise VerificationFailed("run", "the runner stopped (out of memory or crashed)")
    try:
        body = json.loads(done.stdout.decode("utf-8"))
    except ValueError as exc:
        raise LabToolError("the lab runner answered something that is not a result") from exc
    if not body.get("ok"):
        raise VerificationFailed("run", f"{body.get('code', 'failed')}: {body.get('message', '')}")
    values = body["values"]
    if len(values) != len(vectors):
        raise LabToolError("the lab runner returned the wrong number of values")
    return values, float(body.get("slowestCallMs", 0.0)), float(body.get("meanCallMs", 0.0))


def _run(source: str, vectors: list[dict[str, float]]) -> list[float | str]:
    out: list[float | str] = []
    for i in range(0, len(vectors), CHUNK_VECTORS):
        values, slowest, mean = _run_chunk(source, vectors[i : i + CHUNK_VECTORS])
        if mean > MAX_MEAN_CALL_MS or slowest > MAX_CALL_MS:
            raise VerificationFailed(
                "run",
                f"calls took {mean:.1f} ms on average and {slowest:.0f} ms at most "
                f"(limits {MAX_MEAN_CALL_MS:.0f} and {MAX_CALL_MS:.0f} ms): too slow for sliders",
            )
        out.extend(values)
    return out


# ── verification ───────────────────────────────────────────────────────────────────────────────────────────────────────


def verify(contract: LabContract, source: str) -> VerifiedArtifact:
    """Check, run and test `source` against `contract`; return the minted `VerifiedArtifact` or raise `VerificationFailed`."""
    names = [p.name for p in contract.parameters]
    checked = check_source(source, names)
    if not checked.ok:
        first = checked.problems[0]
        raise VerificationFailed("check", f"{first.rule}: {first.message}")

    battery = _battery(contract)
    raw = _run(source, battery.vectors)
    values: list[float] = []
    for v in raw:
        if isinstance(v, str):
            raise VerificationFailed("finite", f"the function returned {v}")
        values.append(float(v))

    for case, got in zip(contract.cases, values[battery.cases], strict=True):
        if abs(got - case.expected) > case.tolerance:
            raise VerificationFailed(
                "reference_cases", f"{case.params} gave {got}, the formula gives {case.expected}"
            )

    reference = REFERENCES[contract.reference]
    grid_values = values[battery.grid]
    for spec in contract.properties:
        if spec.kind == "finite":
            continue  # a non-finite value never gets this far
        if spec.kind == "non_negative":
            worst = min(values)
            if worst < -EPS:
                raise VerificationFailed("non_negative", f"the function returned {worst}")
        elif spec.kind == "bounded":
            assert spec.lo is not None and spec.hi is not None
            if min(values) < spec.lo - EPS or max(values) > spec.hi + EPS:
                raise VerificationFailed(
                    "bounded",
                    f"values reach {min(values)} to {max(values)}, outside [{spec.lo}, {spec.hi}]",
                )
        elif spec.kind == "monotone":
            assert spec.param is not None
            sign = 1 if spec.direction == "increasing" else -1
            stride = battery.strides[spec.param]
            for i in range(len(grid_values) - stride):
                if (i // stride) % (contract.grid + 1) == contract.grid:
                    continue  # the last step of this parameter: its neighbour is another line
                if sign * (grid_values[i + stride] - grid_values[i]) < -EPS:
                    raise VerificationFailed("monotone", f"not {spec.direction} in {spec.param}")
        elif spec.kind == "matches_reference":
            for vector, got in zip(battery.vectors, values, strict=True):
                try:
                    want = float(reference(**vector))
                except (ValueError, OverflowError, ArithmeticError) as exc:
                    raise VerificationFailed(
                        "reference", f"the reference function failed at {vector}"
                    ) from exc
                if not math.isfinite(want) or abs(got - want) > contract.agreement_tolerance * (
                    1 + abs(want)
                ):
                    raise VerificationFailed(
                        "matches_reference", f"{vector} gave {got}, the reference gives {want}"
                    )

    sha = source_sha256(source)
    return _issue(
        lab_id=lab_id_for(contract.id, sha),
        contract_id=contract.id,
        contract_sha256=contract_sha256(contract),
        title=contract.title,
        parameters=contract.parameters,
        source=source,
        source_sha256=sha,
        template_version=TEMPLATE_VERSION,
        checked=Checked(
            reference_cases=len(contract.cases),
            properties=len(contract.properties),
            fuzz_cases=battery.extra.stop - battery.extra.start,
            grid_points=battery.grid.stop - battery.grid.start,
        ),
    )
