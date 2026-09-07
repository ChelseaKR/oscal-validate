"""Capture golden SARIF output of the default validation path.

Run this only from a commit whose output is the one to be preserved.
``tests/test_sarif.py`` compares the live tool against these files, so
regenerating them is a deliberate act that belongs in its own commit with
its reason.

    uv run python tests/sarif/capture.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent

#: (golden name, document relative to the repository root). Relative, and
#: run from the root, so the artifact URIs in the goldens are the same on
#: every machine.
CASES: list[tuple[str, str]] = [
    ("broken_catalog", "tests/fixtures/broken_catalog.json"),
    ("clean_profile", "tests/fixtures/clean_profile.json"),
]


def run(document: str) -> bytes:
    command = [sys.executable, "-m", "oscal_validate", document, "--format", "sarif"]
    result = subprocess.run(command, capture_output=True, check=False, cwd=ROOT)
    return result.stdout + f"\n[exit {result.returncode}]\n".encode()


def main() -> None:
    for name, document in CASES:
        (HERE / f"{name}.sarif.out").write_bytes(run(document))
    print(f"captured {len(CASES)} case(s)")


if __name__ == "__main__":
    main()
