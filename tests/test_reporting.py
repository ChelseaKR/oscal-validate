"""The parts of the report that exist so a reader knows what was not checked."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from oscal_validate import Severity, validate_file
from oscal_validate.cli import main
from oscal_validate.document import _is_json_type, _json_type_of
from oscal_validate.findings import Finding, Rule, counts, finalize, render_findings_text
from oscal_validate.session import Session
from oscal_validate.validator import build_session

from .conftest import fixture_path, load_fixture, write


def _codes(path: Path, resolve: list[Path] | None = None) -> dict[str, int]:
    found: dict[str, int] = {}
    for finding in validate_file(path, resolve):
        found[finding.code] = found.get(finding.code, 0) + 1
    return found


def test_a_clean_run_still_reports_what_it_did_not_check() -> None:
    codes = _codes(fixture_path("clean_catalog.json"))
    assert codes["CONSTRAINT_NOT_EVALUATED"] >= 4
    assert codes["PATTERN_NOT_CHECKED"] == 1
    assert all(
        f.severity is Severity.UNVERIFIABLE
        for f in validate_file(fixture_path("clean_catalog.json"))
    )


def test_the_unchecked_pattern_finding_names_the_datatype_and_the_count() -> None:
    unchecked = next(
        f
        for f in validate_file(fixture_path("clean_catalog.json"))
        if f.code == "PATTERN_NOT_CHECKED"
    )
    assert unchecked.prop == "TokenDatatype"
    assert "value(s)" in unchecked.value
    assert "neither passed nor failed" in unchecked.message


def test_the_constraint_coverage_finding_points_at_the_published_table() -> None:
    findings = [
        f
        for f in validate_file(fixture_path("clean_catalog.json"))
        if f.code == "CONSTRAINT_NOT_EVALUATED"
    ]
    assert findings
    for finding in findings:
        assert "docs/CONSTRAINT-COVERAGE.md" in finding.message
        assert "neither passed nor failed" in finding.message


def test_an_unreadable_schema_construct_is_reported_not_skipped(tmp_path: Path) -> None:
    # A profile import must carry include-all or include-controls. One that
    # carries neither matches no alternative, and that is said out loud.
    profile: Any = copy.deepcopy(load_fixture("clean_profile.json"))
    profile["profile"]["imports"] = [{"href": "somewhere.json"}]
    codes = _codes(write(tmp_path, "p.json", profile))
    assert codes.get("NO_SCHEMA_ALTERNATIVE") == 1


def test_the_import_audit_trail_names_the_file_each_import_matched() -> None:
    findings = validate_file(
        fixture_path("clean_profile.json"), [fixture_path("clean_catalog.json")]
    )
    resolved = next(f for f in findings if f.code == "IMPORT_RESOLVED")
    assert "clean_catalog.json" in resolved.message
    assert resolved.severity is Severity.INFO


def test_the_incompleteness_message_lists_the_missing_documents() -> None:
    session = build_session(fixture_path("clean_profile.json"))
    assert "clean_catalog.json" in session.incompleteness
    assert not session.complete


def test_a_complete_session_has_nothing_to_say_about_incompleteness() -> None:
    session: Session = build_session(
        fixture_path("clean_profile.json"), [fixture_path("clean_catalog.json")]
    )
    assert session.complete
    assert session.incompleteness == ""


def test_the_version_flag_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert "oscal-validate" in capsys.readouterr().out


def test_json_types_are_classified_the_way_json_schema_means_them() -> None:
    assert _json_type_of(True) == "boolean"
    assert _json_type_of(3) == "integer"
    assert _json_type_of(3.5) == "number"
    assert _json_type_of(None) == "null"
    assert _json_type_of("x") == "string"
    assert _is_json_type(3, "number") and _is_json_type(3.5, "number")
    assert not _is_json_type(True, "integer")


def test_findings_are_deduplicated_and_ordered_deterministically() -> None:
    rule = Rule(citation="c", url="u", retrieved="-")
    one = Finding("A", Severity.ERROR, "/b", "p", "v", "m", rule)
    two = Finding("A", Severity.ERROR, "/a", "p", "v", "m", rule)
    assert finalize([one, two, one]) == [two, one]
    assert counts([one, two])["ERROR"] == 2


def test_the_text_report_names_the_model_and_summarizes_every_severity() -> None:
    text = render_findings_text(validate_file(fixture_path("clean_catalog.json")), "catalog")
    assert text.startswith("model: catalog")
    for severity in ("ERROR", "WARNING", "INFO", "UNVERIFIABLE"):
        assert severity in text.rsplit("\n", 1)[-1]


def test_the_json_report_carries_the_model_and_the_tool_version(tmp_path: Path) -> None:
    from oscal_validate import __version__
    from oscal_validate.findings import render_findings_json

    payload = json.loads(
        render_findings_json(
            validate_file(fixture_path("clean_catalog.json")), __version__, "catalog"
        )
    )
    assert payload["tool"]["version"] == __version__
    assert payload["document"]["model"] == "catalog"
    _ = tmp_path
