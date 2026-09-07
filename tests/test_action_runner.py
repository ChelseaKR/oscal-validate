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
import re
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
    # five of them and nothing else, so it passes even at the lowest setting.
    for threshold in ("error", "warning", "info"):
        code, _, outputs = _run(
            tmp_path,
            OSCAL_PATH=str(FIXTURES / "clean_catalog.json"),
            OSCAL_FAIL_ON=threshold,
        )
        assert code == 0, threshold
        assert outputs["unverifiable-count"] == "5"


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


# -- the report the action reads is a contract, and a gap in it is not a zero --


def _stub_cli(tmp_path: Path, report: object, exit_code: int = 0) -> Path:
    """A package that answers ``python -m oscal_validate`` with one report.

    The runner shells out to the CLI, so the only way to hand it a malformed
    report end to end is to be the CLI. This writes a stub package and returns
    the directory to put ahead of ``src`` on ``PYTHONPATH``.
    """
    package = tmp_path / "stub" / "oscal_validate"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        f"import json, sys\nprint(json.dumps({report!r}))\nraise SystemExit({exit_code})\n",
        encoding="utf-8",
    )
    return tmp_path / "stub"


def _run_against_stub(tmp_path: Path, report: object) -> tuple[int, str]:
    stub = _stub_cli(tmp_path, report)
    written = tmp_path / "outputs.txt"
    completed = subprocess.run(
        [sys.executable, str(RUNNER)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": f"{stub}{os.pathsep}{ROOT / 'src'}",
            "GITHUB_OUTPUT": str(written),
            "OSCAL_PATH": str(FIXTURES / "clean_catalog.json"),
        },
        check=False,
    )
    return completed.returncode, completed.stdout


def _whole_report() -> dict[str, Any]:
    return {
        "report_schema_version": "1.0.0",
        "tool": {"name": "oscal-validate", "version": "0.0.0"},
        "document": {"model": "catalog"},
        "findings": [],
        "summary": {"ERROR": 0, "WARNING": 0, "INFO": 0, "UNVERIFIABLE": 0},
    }


def test_the_stub_harness_itself_passes_when_the_report_is_whole(tmp_path: Path) -> None:
    """Without this, every assertion below could be passing for the wrong
    reason -- a stub that never runs also never reports a clean gate."""
    code, stdout = _run_against_stub(tmp_path, _whole_report())
    assert code == 0, stdout


def test_a_summary_missing_a_severity_is_not_read_as_zero(tmp_path: Path) -> None:
    """This is the regression. ``summary.get(severity, 0)`` folded a missing
    ERROR count in as zero and the job passed clean."""
    report = _whole_report()
    report["summary"] = {"WARNING": 0, "INFO": 0, "UNVERIFIABLE": 0}
    code, stdout = _run_against_stub(tmp_path, report)
    assert code == 2, "a report with no ERROR count is unreadable, not clean"
    assert "ERROR" in stdout


def test_a_summary_count_that_is_not_a_number_is_not_read_as_zero(tmp_path: Path) -> None:
    report = _whole_report()
    report["summary"]["ERROR"] = "lots"
    assert _run_against_stub(tmp_path, report)[0] == 2


def test_a_report_with_no_schema_version_is_refused(tmp_path: Path) -> None:
    report = _whole_report()
    del report["report_schema_version"]
    code, stdout = _run_against_stub(tmp_path, report)
    assert code == 2
    assert "report_schema_version" in stdout


def test_a_report_from_a_future_major_is_refused_rather_than_guessed_at(
    tmp_path: Path,
) -> None:
    report = _whole_report()
    report["report_schema_version"] = "2.0.0"
    code, stdout = _run_against_stub(tmp_path, report)
    assert code == 2
    assert "2.0.0" in stdout


def test_a_later_minor_of_the_same_major_is_still_read(tmp_path: Path) -> None:
    """A minor bump adds a key an existing consumer may ignore, so refusing it
    would make every additive change a breaking one."""
    report = _whole_report()
    report["report_schema_version"] = "1.7.0"
    assert _run_against_stub(tmp_path, report)[0] == 0


def test_a_report_that_lost_its_findings_is_refused(tmp_path: Path) -> None:
    report = _whole_report()
    del report["findings"]
    assert _run_against_stub(tmp_path, report)[0] == 2


def test_the_action_reads_the_version_the_package_actually_writes() -> None:
    """The runner's supported major and the package's schema version cannot
    drift apart without this failing."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import action_runner
    finally:
        sys.path.pop(0)
    from oscal_validate import REPORT_SCHEMA_VERSION

    assert REPORT_SCHEMA_VERSION.split(".")[0] == action_runner.SUPPORTED_REPORT_SCHEMA_MAJOR


# -- the SARIF file: complete, or not written at all ----------------------------


def _sarif_run(tmp_path: Path, path: str, **inputs: str) -> tuple[int, str, Path]:
    destination = tmp_path / "out" / "oscal-validate.sarif"
    code, stdout, _ = _run(tmp_path, OSCAL_PATH=path, OSCAL_SARIF_FILE=str(destination), **inputs)
    return code, stdout, destination


def test_no_sarif_is_written_unless_it_is_asked_for(tmp_path: Path) -> None:
    code, _, _ = _run(tmp_path, OSCAL_PATH=str(FIXTURES / "clean_catalog.json"))
    assert code == 0
    assert not list(tmp_path.rglob("*.sarif"))


def test_the_sarif_file_carries_every_document_as_one_run(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    for name in ("clean_catalog.json", "clean_profile.json"):
        (documents / name).write_bytes((ROOT / FIXTURES / name).read_bytes())

    code, stdout, destination = _sarif_run(tmp_path, str(documents))
    assert code == 0, stdout
    log = json.loads(destination.read_text(encoding="utf-8"))
    assert log["version"] == "2.1.0"
    assert len(log["runs"]) == 1, "GitHub accepts at most twenty runs in one file"
    run = log["runs"][0]
    assert [d["path"] for d in run["properties"]["documents"]] == [
        (documents / name).as_uri() for name in ("clean_catalog.json", "clean_profile.json")
    ]
    assert run["results"], "a run that reports nothing at all is not a clean run"
    rules = run["tool"]["driver"]["rules"]
    for result in run["results"]:
        assert rules[result["ruleIndex"]]["id"] == result["ruleId"]


def test_the_sarif_file_records_which_vendored_snapshot_decided_it(tmp_path: Path) -> None:
    code, stdout, destination = _sarif_run(tmp_path, str(FIXTURES / "clean_catalog.json"))
    assert code == 0, stdout
    log = json.loads(destination.read_text(encoding="utf-8"))
    recorded = log["runs"][0]["tool"]["driver"]["properties"]["vendoredSnapshot"]
    assert recorded["algorithm"] == "sha256"
    assert len(recorded["files"]) >= 14


def test_findings_still_gate_the_job_with_sarif_requested(tmp_path: Path) -> None:
    """`fail-on` is unchanged by asking for SARIF, and the file is still
    written for a run that fails: those are the findings to upload."""
    broken = _broken_catalog(tmp_path)
    code, stdout, destination = _sarif_run(tmp_path, str(broken))
    assert code == 1, stdout
    assert json.loads(destination.read_text(encoding="utf-8"))["runs"][0]["results"]


def test_no_sarif_is_written_when_a_document_could_not_be_read(tmp_path: Path) -> None:
    """An upload resolves the alerts it omits, so a file missing a document's
    findings is worse than no file: it closes real alerts as fixed."""
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "clean_catalog.json").write_bytes(
        (ROOT / FIXTURES / "clean_catalog.json").read_bytes()
    )
    (documents / "broken.json").write_text("{ not json", encoding="utf-8")

    code, stdout, destination = _sarif_run(tmp_path, str(documents))
    assert code == 2, stdout
    assert not destination.exists(), "a partial SARIF file must never be written"
    assert "resolves the alerts it omits" in stdout


def _sarif_stub(tmp_path: Path, report: object, sarif: object) -> Path:
    """A stub CLI that answers both formats, so the two can be made to disagree.

    This one replaces the command-line entry point and *only* that: its
    ``__init__`` extends ``__path__`` back over the real package, so
    ``oscal_validate.sarif`` -- which the runner imports to merge -- is still
    the real module. A whole-package stub would shadow it, and the runner
    would then fail on an import error rather than on the thing under test.
    """
    package = tmp_path / "stub" / "oscal_validate"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        f"__path__.append({str(ROOT / 'src' / 'oscal_validate')!r})\n", encoding="utf-8"
    )
    (package / "__main__.py").write_text(
        "import json, sys\n"
        f"print(json.dumps({sarif!r} if '--format' in sys.argv and "
        f"sys.argv[sys.argv.index('--format') + 1] == 'sarif' else {report!r}))\n",
        encoding="utf-8",
    )
    return tmp_path / "stub"


def _run_with_sarif_stub(tmp_path: Path, report: object, sarif: object) -> tuple[int, str, Path]:
    stub = _sarif_stub(tmp_path, report, sarif)
    destination = tmp_path / "oscal-validate.sarif"
    completed = subprocess.run(
        [sys.executable, str(RUNNER)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": f"{stub}{os.pathsep}{ROOT / 'src'}",
            "GITHUB_OUTPUT": str(tmp_path / "outputs.txt"),
            "OSCAL_PATH": str(FIXTURES / "clean_catalog.json"),
            "OSCAL_SARIF_FILE": str(destination),
        },
        check=False,
    )
    return completed.returncode, completed.stdout, destination


def _whole_sarif(results: int) -> dict[str, Any]:
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "oscal-validate",
                        "properties": {},
                        "rules": [
                            {
                                "id": "X",
                                "name": "X",
                                "properties": {
                                    "sources": [
                                        {
                                            "url": "https://example.invalid/x",
                                            "retrieved": "2026-01-01",
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                },
                "results": [
                    {"ruleId": "X", "ruleIndex": 0, "message": {"text": "x"}}
                    for _ in range(results)
                ],
                "properties": {
                    "document": {"model": "catalog", "path": "x.json"},
                    "summary": {"ERROR": 0, "WARNING": 0, "INFO": 0, "UNVERIFIABLE": results},
                },
            }
        ],
    }


def _report_with(findings: int) -> dict[str, Any]:
    report = _whole_report()
    report["findings"] = [
        {
            "code": "X",
            "severity": "UNVERIFIABLE",
            "location": "/catalog",
            "property": "p",
            "value": "v",
            "message": "m",
            "rule": {"citation": "c", "url": "u", "retrieved": "r"},
        }
        for _ in range(findings)
    ]
    report["summary"]["UNVERIFIABLE"] = findings
    return report


def test_the_sarif_stub_harness_itself_passes_when_the_two_agree(tmp_path: Path) -> None:
    """Without this every assertion below could pass for the wrong reason."""
    code, stdout, destination = _run_with_sarif_stub(tmp_path, _report_with(2), _whole_sarif(2))
    assert code == 0, stdout
    assert destination.exists()


def test_a_sarif_run_that_lost_a_result_is_refused_not_uploaded(tmp_path: Path) -> None:
    """Two renderings of one list of findings cannot legitimately disagree,
    and the smaller one is the one that would be uploaded."""
    code, stdout, destination = _run_with_sarif_stub(tmp_path, _report_with(2), _whole_sarif(1))
    assert code == 2, stdout
    assert not destination.exists()
    assert "1 result(s)" in stdout and "2 finding(s)" in stdout


def test_sarif_that_is_not_one_run_is_refused(tmp_path: Path) -> None:
    log = _whole_sarif(0)
    log["runs"] = log["runs"] + log["runs"]
    code, stdout, destination = _run_with_sarif_stub(tmp_path, _report_with(0), log)
    assert code == 2, stdout
    assert not destination.exists()
    assert "exactly one run" in stdout


def test_the_action_inputs_and_the_runner_read_the_same_environment(tmp_path: Path) -> None:
    """A renamed input does not fail; it arrives as an empty string, and the
    feature it controls silently does nothing. This is the only thing that
    notices."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import action_runner
    finally:
        sys.path.pop(0)
    source = Path(action_runner.__file__).read_text(encoding="utf-8")
    read = set(re.findall(r'os\.environ\.get\("(OSCAL_[A-Z_]+)"\)', source))
    passed = set(
        re.findall(r"^\s+(OSCAL_[A-Z_]+):", (ROOT / "action.yml").read_text("utf-8"), re.M)
    )
    assert read == passed, "action.yml and the runner disagree about the environment"
