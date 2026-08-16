"""Break the action's gate on purpose, before anyone depends on it.

`action.yml` is a gate other repositories will put in front of their own
delivery step, and a gate that cannot fail is worse than no gate at all. These
tests run the action's entry point exactly as the composite step runs it, same
interpreter and same environment variables, and assert the exit code it hands
back to GitHub: 0 clean, 1 gated findings, 2 unusable input. The broken
documents start from a fixture proven clean and break exactly one thing, which
is the discipline `tests/test_break_the_gate.py` uses on the CLI.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .conftest import load_fixture

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tools" / "action_runner.py"
FIXTURES = Path("tests") / "fixtures"


def _run(tmp_path: Path, **inputs: str) -> tuple[int, str, dict[str, str]]:
    """Invoke the runner the way the composite step does, from the repo root."""
    written = tmp_path / "outputs.txt"
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "GITHUB_OUTPUT": str(written),
        **inputs,
    }
    completed = subprocess.run(
        [sys.executable, str(RUNNER)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=environment,
        check=False,
    )
    # Nothing is written when the run rejects its inputs before validating.
    raw = written.read_text(encoding="utf-8") if written.exists() else ""
    outputs = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
    return completed.returncode, completed.stdout, outputs


def _broken_catalog(tmp_path: Path) -> Path:
    """A proven-clean catalog with exactly one required property removed."""
    catalog: Any = copy.deepcopy(load_fixture("clean_catalog.json"))
    del catalog["catalog"]["metadata"]["last-modified"]
    path = tmp_path / "broken_catalog.json"
    path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    return path


def test_a_clean_document_passes(tmp_path: Path) -> None:
    code, _, outputs = _run(tmp_path, OSCAL_PATH=str(FIXTURES / "clean_catalog.json"))
    assert code == 0
    assert outputs["error-count"] == "0"
    assert outputs["files-validated"] == "1"


def test_an_error_finding_fails_the_job(tmp_path: Path) -> None:
    broken = _broken_catalog(tmp_path)
    code, stdout, outputs = _run(tmp_path, OSCAL_PATH=str(broken))
    assert code == 1, "an ERROR finding must fail the job"
    assert outputs["error-count"] == "1"
    assert "::error file=" in stdout, "the failing finding must be annotated on the file"


def test_unverifiable_never_gates_at_any_threshold(tmp_path: Path) -> None:
    # UNVERIFIABLE is never a pass and never a fail. The clean catalog reports
    # seven of them and nothing else, so it passes even at the lowest setting.
    for threshold in ("error", "warning", "info"):
        code, _, outputs = _run(
            tmp_path,
            OSCAL_PATH=str(FIXTURES / "clean_catalog.json"),
            OSCAL_FAIL_ON=threshold,
        )
        assert code == 0, threshold
        assert outputs["unverifiable-count"] == "7"


def test_lowering_the_threshold_gates_on_an_informational_finding(tmp_path: Path) -> None:
    document = str(FIXTURES / "clean_profile.json")
    assert _run(tmp_path, OSCAL_PATH=document)[0] == 0
    assert _run(tmp_path, OSCAL_PATH=document, OSCAL_FAIL_ON="info")[0] == 1


def test_resolve_reaches_the_cli(tmp_path: Path) -> None:
    # Supplying the imported catalog settles three references that are
    # unverifiable without it.
    document = str(FIXTURES / "clean_profile.json")
    alone = _run(tmp_path, OSCAL_PATH=document)[2]
    resolved = _run(
        tmp_path, OSCAL_PATH=document, OSCAL_RESOLVE=str(FIXTURES / "clean_catalog.json")
    )
    assert int(resolved[2]["unverifiable-count"]) < int(alone["unverifiable-count"])


def test_a_document_that_cannot_be_read_is_a_failure_not_a_pass(tmp_path: Path) -> None:
    code, _, _ = _run(tmp_path, OSCAL_PATH=str(FIXTURES / "no-such-document.json"))
    assert code == 2


def test_one_unreadable_document_fails_a_run_of_otherwise_clean_ones(tmp_path: Path) -> None:
    (tmp_path / "clean.json").write_text(
        json.dumps(load_fixture("clean_catalog.json")), encoding="utf-8"
    )
    (tmp_path / "truncated.json").write_text("{", encoding="utf-8")
    code, _, outputs = _run(tmp_path, OSCAL_PATH=str(tmp_path / "*.json"))
    assert code == 2
    assert outputs["files-validated"] == "1"


def test_a_path_matching_nothing_is_a_failure_not_a_pass(tmp_path: Path) -> None:
    code, stdout, _ = _run(tmp_path, OSCAL_PATH=str(FIXTURES / "*.no-such-suffix"))
    assert code == 2
    assert "not a pass" in stdout


def test_an_unusable_fail_on_is_rejected_rather_than_ignored(tmp_path: Path) -> None:
    code, _, _ = _run(
        tmp_path, OSCAL_PATH=str(FIXTURES / "clean_catalog.json"), OSCAL_FAIL_ON="whenever"
    )
    assert code == 2


def test_a_directory_is_validated_recursively_and_one_bad_file_fails_it(tmp_path: Path) -> None:
    _broken_catalog(tmp_path)
    (tmp_path / "clean.json").write_text(
        json.dumps(load_fixture("clean_catalog.json")), encoding="utf-8"
    )
    code, _, outputs = _run(tmp_path, OSCAL_PATH=str(tmp_path))
    assert code == 1
    assert outputs["files-validated"] == "2"
    assert outputs["error-count"] == "1"
