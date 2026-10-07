"""P4 V7: run the VerifiedLab mutation suite and write its detection rate (D-36). Free: no model call, no embedding.

    uv run python eval/lab_mutations.py             # prints the summary
    uv run python eval/lab_mutations.py --write     # also writes eval/results/<stamp>-p4-lab-mutations.json

Every planted defect is run through the real stage that must catch it; a defect refused by a different stage is a miss.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from api.labs.mutations import run_suite, summary

RESULTS = Path(__file__).resolve().parent / "results"


def main(argv: list[str]) -> int:
    outcomes = run_suite()
    report = summary(outcomes)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    body = {"commit": commit, "summary": report, "outcomes": [o.__dict__ for o in outcomes]}
    print(json.dumps(report, indent=2))
    if "--write" in argv:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = RESULTS / f"{stamp}-p4-lab-mutations.json"
        path.write_text(json.dumps(body, indent=2), encoding="utf-8")
        print(f"wrote {path}")
    return 0 if report["overall"]["detected"] == report["overall"]["planted"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
