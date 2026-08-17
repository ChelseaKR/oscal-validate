"""CLI behavior: exit codes, formats, bad input."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from oscal_validate import __version__
from oscal_validate.cli import main

from .conftest import fixture_path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_the_version_the_tool_reports_is_the_version_it_is() -> None:
    """``--version`` and every JSON report stamp ``__version__``, not the manifest.

    They drifted: 0.2.0 shipped with the package still reporting 0.1.0 in
    ``--version`` and in ``tool.version`` on every machine-readable report, so
    a stored report named the wrong release of the rules that produced it.
    """
    manifest = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert __version__ == manifest["project"]["version"]


def test_clean_catalog_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(fixture_path("clean_catalog.json"))]) == 0
    out = capsys.readouterr().out
    assert "model: catalog" in out
    assert "0 ERROR" in out


def test_unverifiable_alone_does_not_gate(capsys: pytest.CaptureFixture[str]) -> None:
    # A clean run still reports what it could not evaluate, and still exits 0.
    assert main([str(fixture_path("clean_catalog.json"))]) == 0
    assert "UNVERIFIABLE" in capsys.readouterr().out


def test_error_findings_exit_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"catalog": {"metadata": {}}}), encoding="utf-8")
    assert main([str(broken)]) == 1
    out = capsys.readouterr().out
    assert "REQUIRED_PROPERTY_MISSING" in out
    assert "rule:" in out and "source:" in out


def test_json_format_is_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([str(fixture_path("clean_catalog.json")), "--format", "json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tool"]["name"] == "oscal-validate"
    assert payload["document"]["model"] == "catalog"
    assert payload["summary"]["ERROR"] == 0
    for finding in payload["findings"]:
        assert finding["rule"]["citation"]
        assert finding["rule"]["url"]


def test_resolve_completes_the_effective_data_model(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog = fixture_path("clean_catalog.json")
    profile = fixture_path("clean_profile.json")
    assert main([str(profile)]) == 0
    unresolved = capsys.readouterr().out
    assert "REFERENCE_UNVERIFIABLE" in unresolved
    assert "IMPORT_NOT_SUPPLIED" in unresolved

    assert main([str(profile), "--resolve", str(catalog)]) == 0
    resolved = capsys.readouterr().out
    assert "REFERENCE_UNVERIFIABLE" not in resolved
    assert "IMPORT_RESOLVED" in resolved
    _ = tmp_path


def test_resolve_accepts_a_directory() -> None:
    profile = fixture_path("clean_profile.json")
    assert main([str(profile), "--resolve", str(fixture_path("clean_catalog.json").parent)]) == 0


def test_missing_file_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["/nonexistent/nope.json"]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_invalid_json_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert main([str(bad)]) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_a_document_that_is_not_oscal_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    other = tmp_path / "other.json"
    other.write_text('{"something-else": {}}', encoding="utf-8")
    assert main([str(other)]) == 2
    assert "no OSCAL model root" in capsys.readouterr().err


def test_two_model_roots_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    both = tmp_path / "both.json"
    both.write_text('{"catalog": {}, "profile": {}}', encoding="utf-8")
    assert main([str(both)]) == 2
    assert "more than one OSCAL model root" in capsys.readouterr().err


def test_a_scalar_document_exits_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    scalar = tmp_path / "scalar.json"
    scalar.write_text('"just a string"', encoding="utf-8")
    assert main([str(scalar)]) == 2
    assert "expected a JSON object" in capsys.readouterr().err
