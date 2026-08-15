"""Keep the scanner exceptions narrow and the gates blocking."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
SEMGREP = WORKFLOWS / "semgrep.yml"
TRUFFLEHOG = WORKFLOWS / "trufflehog.yml"
PYTHON_COMPATIBILITY_RULE = "python.lang.compatibility.python37.python37-compatibility-importlib2"

BROAD_BYPASSES = ("continue-on-error", "|| true", "|| :", "--no-error", "--suppress-errors")


def test_python_policy_is_aligned_on_312() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["project"]["requires-python"] == ">=3.12"
    assert config["tool"]["mypy"]["python_version"] == "3.12"
    assert config["tool"]["ruff"]["target-version"] == "py312"
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12"


def test_every_action_is_pinned_to_a_full_commit_sha() -> None:
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for reference in re.findall(r"uses:\s*(\S+)", text):
            assert re.search(r"@[0-9a-f]{40}$", reference), f"{workflow.name}: {reference}"


def test_the_semgrep_exception_is_exact_and_the_gate_stays_blocking() -> None:
    workflow = SEMGREP.read_text(encoding="utf-8")
    command = " ".join(workflow.split())
    assert command.count("semgrep ci --config auto") == 1
    assert workflow.count("--exclude-rule") == 1
    assert workflow.count(PYTHON_COMPATIBILITY_RULE) == 1
    assert all(bypass not in workflow for bypass in BROAD_BYPASSES)
    assert re.search(r"--exclude(?:\s|=)", workflow) is None


def test_the_only_semgrep_suppression_is_the_vendored_xml_parse_and_it_is_justified() -> None:
    # A `nosemgrep` is a claim that a rule does not apply here. It has to stay
    # rare, has to name the rule, and has to be defended by something other than
    # the comment beside it: in this case, a guard that refuses a DTD outright.
    sources = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "tools").rglob("*.py"))
    suppressed = [path for path in sources if "nosemgrep" in path.read_text(encoding="utf-8")]
    assert [path.name for path in suppressed] == ["metaschema.py"]

    text = (ROOT / "src" / "oscal_validate" / "metaschema.py").read_text(encoding="utf-8")
    assert text.count("nosemgrep") == 1
    assert "nosemgrep: python.lang.security.use-defused-xml-parse" in text
    assert 'FORBIDDEN_MARKUP = (b"<!DOCTYPE", b"<!ENTITY")' in text


def test_the_secret_scan_excludes_one_known_false_positive_and_nothing_else() -> None:
    workflow = TRUFFLEHOG.read_text(encoding="utf-8")
    assert "--only-verified" in workflow
    assert workflow.count("--exclude-detectors=") == 1
    assert "--exclude-detectors=Lob" in workflow
    assert "--exclude-paths" not in workflow, "excluding paths would blind the scan to fixtures"
    assert "fetch-depth: 0" in workflow, "a history scan needs the whole history"
    assert all(bypass not in workflow for bypass in BROAD_BYPASSES)
