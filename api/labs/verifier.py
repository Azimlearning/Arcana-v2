"""The lab verifier and the mint (P4 V3, D-36): the only code that can create a `VerifiedArtifact`.

`verify(contract, source)` runs, in order: the checker (the AST allowlist), then the isolated runner on a fixed battery of parameter
vectors (the contract's reference cases, a sweep of every parameter with the others at three settings, the corners of the parameter box,
and a seeded fuzz), then the contract's properties and its Python reference function. Only if every stage passes does it construct a
`VerifiedArtifact`. Any failure is a `VerificationFailed` naming the stage and the reason; the source is never trusted and never
evaluated in this process (the runner is a Node child process).

`VerifiedArtifact` is the type the delivery path accepts (hard constraint 3). It can only be built by presenting the module-private mint
token, which no other module imports; a test scans the repository for any other construction. That is a convention made checkable, not
a language guarantee: Python cannot stop code in the same process from forging an object, and this process never runs generated code.
The second line is downstream: the validator re-derives a block from the stored record and the store refuses a hash that does not match.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
from dataclasses import dataclass
from itertools import pairwise, product
from typing import Any

from api.labs.checker import TOOL_DIR, LabToolError, check_source, node_path
from api.labs.contract import REFERENCES, LabContract, LabParameter

TEMPLATE_VERSION = 1
"""The version of the fixed template the web host holds (`web/lib/labFrame.ts`, V6). A block built for another version is refused."""
FUZZ_SEED = 20261008
FUZZ_CASES = 200
RUN_TIMEOUT_SECONDS = 30
PER_CALL_TIMEOUT_MS = 500
MAX_RUNNER_MEMORY_MB = 64
EPS = 1e-12

_MINT = object()


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


class VerifiedArtifact:
    """What the verifier mints: a lab function that passed every stage, with the hash and the counts of what was checked."""

    __slots__ = (
        "_frozen",
        "checked",
        "contract_id",
        "lab_id",
        "parameters",
        "source",
        "source_sha256",
        "template_version",
        "title",
    )

    lab_id: str
    contract_id: str
    title: str
    parameters: tuple[LabParameter, ...]
    source: str
    source_sha256: str
    template_version: int
    checked: Checked

    def __init__(self, *, _mint: object = None, **fields: Any):
        if _mint is not _MINT:
            raise MintRefused("a VerifiedArtifact can only be created by the verifier")
        for name, value in fields.items():
            object.__setattr__(self, name, value)
        for name in self.__slots__:
            if name != "_frozen" and not hasattr(self, name):
                raise MintRefused(f"a VerifiedArtifact needs {name}")
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("a VerifiedArtifact cannot be changed")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("a VerifiedArtifact cannot be changed")

    def __repr__(self) -> str:
        return f"VerifiedArtifact({self.lab_id})"


def source_sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def lab_id_for(contract_id: str, sha: str) -> str:
    return f"{contract_id}-{sha[:12]}"


# ── the battery of parameter vectors ───────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Battery:
    vectors: list[dict[str, float]]
    cases: slice
    sweeps: dict[str, list[tuple[float, slice]]]
    """For each parameter, the sweeps of it: the setting of the others (as a label) and where its vectors lie."""
    extra: slice
    """The corners and the fuzz."""


def _linspace(p: LabParameter, n: int) -> list[float]:
    return [p.min + (p.max - p.min) * i / (n - 1) for i in range(n)]


def _battery(contract: LabContract) -> _Battery:
    vectors: list[dict[str, float]] = [dict(case.params) for case in contract.cases]
    cases = slice(0, len(vectors))
    sweeps: dict[str, list[tuple[float, slice]]] = {}
    for swept in contract.parameters:
        sweeps[swept.name] = []
        for setting in (0, 1, 2):  # the others at their defaults, at their minima, at their maxima
            start = len(vectors)
            for x in _linspace(swept, contract.sweep_points):
                vector = {
                    q.name: (q.default, q.min, q.max)[setting] if q.name != swept.name else x
                    for q in contract.parameters
                }
                vectors.append(vector)
            sweeps[swept.name].append((float(setting), slice(start, len(vectors))))
    start = len(vectors)
    levels = [(q.min, (q.min + q.max) / 2, q.max) for q in contract.parameters]
    for combo in product(*levels):
        vectors.append({q.name: v for q, v in zip(contract.parameters, combo, strict=True)})
    rng = random.Random(FUZZ_SEED)
    for _ in range(FUZZ_CASES):
        vectors.append({q.name: rng.uniform(q.min, q.max) for q in contract.parameters})
    return _Battery(vectors, cases, sweeps, slice(start, len(vectors)))


# ── running ─────────────────────────────────────────────────────────────────────────────────────────────────────────────


def _run(source: str, vectors: list[dict[str, float]]) -> list[float | str]:
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
    return values


# ── verification ───────────────────────────────────────────────────────────────────────────────────────────────────────


def verify(contract: LabContract, source: str) -> VerifiedArtifact:
    """Check, run and test `source` against `contract`; return the minted artifact or raise `VerificationFailed`."""
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
            for _setting, where in battery.sweeps[spec.param]:
                series = values[where]
                if any(sign * (b - a) < -EPS for a, b in pairwise(series)):
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
    return VerifiedArtifact(
        _mint=_MINT,
        lab_id=lab_id_for(contract.id, sha),
        contract_id=contract.id,
        title=contract.title,
        parameters=contract.parameters,
        source=source,
        source_sha256=sha,
        template_version=TEMPLATE_VERSION,
        checked=Checked(
            reference_cases=len(contract.cases),
            properties=len(contract.properties),
            fuzz_cases=battery.extra.stop - battery.extra.start,
        ),
    )
