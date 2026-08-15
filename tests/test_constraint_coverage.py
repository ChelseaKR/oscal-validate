"""The published coverage table must match the vendored files it describes.

A repository that publishes "78 of 340 constraints" and then quietly drifts is
making a claim it no longer checks. `make coverage-doc` regenerates the file;
this test fails if the committed copy is stale.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COVERAGE = ROOT / "docs" / "CONSTRAINT-COVERAGE.md"


def _generated() -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "constraint_coverage.py"), "/dev/stdout"],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.rsplit("wrote /dev/stdout", 1)[0]


def test_the_committed_coverage_table_is_current() -> None:
    assert COVERAGE.read_text(encoding="utf-8") == _generated()


def test_the_coverage_table_lists_every_constraint() -> None:
    from oscal_validate.metaschema import load_metaschema

    text = COVERAGE.read_text(encoding="utf-8")
    for constraint in load_metaschema().constraints:
        if constraint.identifier:
            assert f"`{constraint.identifier}`" in text, constraint.identifier


def test_the_coverage_table_never_claims_a_clean_run_means_conformance() -> None:
    text = COVERAGE.read_text(encoding="utf-8")
    assert "Neither passed nor failed" in text
    assert "may still violate any of these" in text
