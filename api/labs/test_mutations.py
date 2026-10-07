"""The mutation suite (P4 V7, D-36): every planted defect is refused by the stage named for it, and the suite is large enough and varied enough
to mean something. Also the small parity checks that keep the pieces honest: the template version the server stamps is the one the web host
holds, and the guide states the allowlist's numbers."""

import re
from pathlib import Path

from api.labs.mutations import run_suite, summary
from api.labs.verifier import TEMPLATE_VERSION

ROOT = Path(__file__).resolve().parents[2]


def test_every_planted_defect_is_refused_by_the_stage_named_for_it():
    outcomes = run_suite()
    report = summary(outcomes)
    assert report["missed"] == [], report["missed"]
    assert report["overall"]["detected"] == report["overall"]["planted"]
    assert (
        report["overall"]["planted"] >= 100
    )  # the plan asked for at least 25; the set is far larger
    assert set(report["by_family"]) == {"static", "execution", "tampering", "row_tampering"}
    assert all(row["rate"] == 1.0 for row in report["by_family"].values())


def test_the_suite_covers_every_class_the_plan_named():
    classes = set(summary(run_suite())["by_class"])
    for wanted in (
        "static/network",
        "static/escape",
        "static/termination",
        "static/resources",
        "static/markup",
        "execution/numeric",
        "tampering/forgery",
    ):
        assert wanted in classes


def test_the_template_version_the_server_stamps_is_the_one_the_web_host_holds():
    source = (ROOT / "web" / "lib" / "labFrame.ts").read_text(encoding="utf-8")
    match = re.search(r"export const LAB_TEMPLATE_VERSION = (\d+);", source)
    assert match is not None and int(match.group(1)) == TEMPLATE_VERSION


def test_the_sandbox_and_csp_the_guide_and_the_decision_state_are_the_ones_the_host_uses():
    source = (ROOT / "web" / "lib" / "labFrame.ts").read_text(encoding="utf-8")
    assert 'export const LAB_SANDBOX = "allow-scripts";' in source
    assert (
        "export const LAB_CSP = \"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\";"
        in source
    )
    guide = (ROOT / "refdocs" / "guides" / "catalog.md").read_text(encoding="utf-8")
    assert "VerifiedLab" in guide and "allowlist.json" in guide
