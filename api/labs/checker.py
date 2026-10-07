"""The lab checker (P4 V2, D-36): static analysis of a generated function by an AST allowlist, run as a Node subprocess.

The rules live in `packages/labs-check/check.mjs` and `allowlist.json` (one reviewable list). This module only calls it: it hands the
source on stdin, with the contract's parameter names, and reads a JSON verdict. It never evaluates the source. If Node or the checker
is missing, or answers anything but a verdict, the result is a refusal (`LabToolError`), never a pass: the lab tier is unavailable and
nothing can be minted.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[2] / "packages" / "labs-check"
ALLOWLIST_PATH = TOOL_DIR / "allowlist.json"
CHECK_TIMEOUT_SECONDS = 10
MAX_SOURCE_CHARS = 4000
"""The same cap as `allowlist.json`'s `max_source_chars` (a test pins them together)."""


class LabToolError(RuntimeError):
    """The checker or the runner could not give a verdict. The caller treats it as a refusal."""


@dataclass(frozen=True)
class Problem:
    rule: str
    message: str
    line: int
    column: int


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    problems: tuple[Problem, ...]

    @property
    def rules(self) -> tuple[str, ...]:
        return tuple(p.rule for p in self.problems)


def node_path() -> str:
    found = shutil.which("node")
    if found is None:
        raise LabToolError("Node is not installed: the lab checker cannot run")
    return found


def check_source(source: str, param_names: list[str]) -> CheckResult:
    """The checker's verdict on `source`, which may use `p.<name>` for the names in `param_names` only."""
    if (
        len(source) > MAX_SOURCE_CHARS
    ):  # before anything is spawned: an untrusted generator cannot make this tool read without limit
        return CheckResult(
            False,
            (
                Problem(
                    "source_too_large",
                    f"the source is longer than {MAX_SOURCE_CHARS} characters",
                    0,
                    0,
                ),
            ),
        )
    try:
        payload = source.encode("utf-8")
    except UnicodeEncodeError:  # a lone surrogate: not text a function can be made of
        return CheckResult(
            False,
            (
                Problem(
                    "source_not_text", "the source holds a character that is not valid text", 0, 0
                ),
            ),
        )
    script = TOOL_DIR / "check.mjs"
    if not script.exists():
        raise LabToolError("the lab checker is missing")
    try:
        done = subprocess.run(
            [node_path(), str(script), "--params", ",".join(param_names)],
            input=payload,
            capture_output=True,
            timeout=CHECK_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LabToolError("the lab checker timed out") from exc
    if done.returncode != 0:
        raise LabToolError("the lab checker failed")
    try:
        body = json.loads(done.stdout.decode("utf-8"))
        problems = tuple(
            Problem(str(p["rule"]), str(p["message"]), int(p["line"]), int(p["column"]))
            for p in body["problems"]
        )
        ok = bool(body["ok"])
    except (ValueError, KeyError, TypeError) as exc:
        raise LabToolError("the lab checker answered something that is not a verdict") from exc
    if ok != (len(problems) == 0):
        raise LabToolError("the lab checker's verdict disagrees with its problems")
    return CheckResult(ok, problems)
