"""``--format sarif``: the same findings, in SARIF 2.1.0, with no pass invented.

Three things are pinned here. The output validates against the vendored
OASIS schema, offline. It carries exactly the findings the canonical JSON
report carries, in the same order, with the same citation on each. And the
severity mapping never produces ``kind: pass``: an UNVERIFIABLE finding is
``open``, and a report's results are never empty.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft4Validator

from oscal_validate import __version__, validate_file
from oscal_validate.cli import main
from oscal_validate.findings import Finding, Rule, Severity, render_findings_json
from oscal_validate.sarif import (
    DESCRIPTIONS,
    FINGERPRINT,
    KINDS,
    _split_location,
    render_findings_sarif,
)
from oscal_validate.validator import build_session, validate

from .conftest import fixture_path, load_fixture, write
from .sarif.capture import CASES, HERE, ROOT, run

SCHEMA = json.loads((HERE / "sarif-schema-2.1.0.json").read_text(encoding="utf-8"))
CHECKS = ROOT / "src" / "oscal_validate" / "checks"


def _sarif(document: Path, resolve: list[Path] | None = None) -> dict[str, Any]:
    session = build_session(document, resolve)
    model = session.corpus.primary.walked.model
    log: dict[str, Any] = json.loads(
        render_findings_sarif(validate(session), __version__, model, document)
    )
    return log


def _report(document: Path, resolve: list[Path] | None = None) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(
        render_findings_json(validate_file(document, resolve), __version__, "catalog")
    )
    return report


# -- the schema, offline -------------------------------------------------------


def test_the_vendored_schema_is_the_sarif_2_1_0_schema() -> None:
    assert SCHEMA["id"].endswith("/sarif-schema-2.1.0.json")
    assert SCHEMA["properties"]["version"]["enum"] == ["2.1.0"]
    Draft4Validator.check_schema(SCHEMA)


@pytest.mark.parametrize(
    ("document", "resolve"),
    [
        ("clean_catalog.json", []),
        ("broken_catalog.json", []),
        ("clean_profile.json", []),
        ("clean_profile.json", ["clean_catalog.json"]),
        ("nist_ssp_example.json", []),
    ],
)
def test_every_report_validates_against_the_sarif_schema(document: str, resolve: list[str]) -> None:
    log = _sarif(fixture_path(document), [fixture_path(r) for r in resolve])
    errors = sorted(Draft4Validator(SCHEMA).iter_errors(log), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)


# -- the goldens ---------------------------------------------------------------


@pytest.mark.parametrize(("name", "document"), CASES)
def test_the_cli_reproduces_the_golden_sarif_bytes(name: str, document: str) -> None:
    expected = (HERE / f"{name}.sarif.out").read_bytes()
    assert run(document) == expected, f"{name} drifted from the golden"


def test_sarif_output_is_byte_identical_across_processes() -> None:
    command = [
        sys.executable,
        "-m",
        "oscal_validate",
        str(fixture_path("clean_profile.json")),
        "--resolve",
        str(fixture_path("clean_catalog.json")),
        "--format",
        "sarif",
    ]
    runs = [subprocess.run(command, capture_output=True, check=False) for _ in range(2)]
    assert runs[0].stdout == runs[1].stdout
    assert runs[0].stdout
    json.loads(runs[0].stdout)


# -- the same findings as the canonical report ---------------------------------


def test_sarif_carries_every_finding_of_the_json_report_in_the_same_order() -> None:
    document = fixture_path("broken_catalog.json")
    report = _report(document)
    results = _sarif(document)["runs"][0]["results"]
    assert len(results) == len(report["findings"]) > 0
    for finding, result in zip(report["findings"], results, strict=True):
        assert result["ruleId"] == finding["code"]
        assert result["properties"]["severity"] == finding["severity"]
        assert result["properties"]["location"] == finding["location"]
        assert result["properties"]["property"] == finding["property"]
        assert result["properties"]["value"] == finding["value"]
        assert result["properties"]["rule"] == finding["rule"]
        assert finding["message"] in result["message"]["text"]
        assert finding["rule"]["citation"] in result["message"]["text"]
        assert f"retrieved {finding['rule']['retrieved']}" in result["message"]["text"]


def test_the_run_summary_is_the_json_reports_summary() -> None:
    document = fixture_path("broken_catalog.json")
    run_properties = _sarif(document)["runs"][0]["properties"]
    assert run_properties["summary"] == _report(document)["summary"]
    assert run_properties["summary"]["ERROR"] == 3


def test_the_tool_names_itself_and_its_version() -> None:
    driver = _sarif(fixture_path("clean_catalog.json"))["runs"][0]["tool"]["driver"]
    assert driver["name"] == "oscal-validate"
    assert driver["version"] == __version__
    assert driver["informationUri"].startswith("https://")


# -- severities: never a pass ---------------------------------------------------


def test_error_is_a_fail_and_unverifiable_is_open() -> None:
    assert KINDS[Severity.ERROR] == ("fail", "error")
    assert KINDS[Severity.WARNING] == ("fail", "warning")
    assert KINDS[Severity.UNVERIFIABLE][0] == "open"
    assert KINDS[Severity.INFO][0] == "informational"
    # Every non-fail result keeps a level GitHub renders. ``none`` would hide
    # it, which is the absence-as-pass this tool refuses. See sarif.py.
    for kind, level in KINDS.values():
        assert level in ("error", "warning", "note"), (kind, level)
    assert "pass" not in {kind for kind, _ in KINDS.values()}


def test_no_result_is_ever_a_pass_and_a_clean_document_still_has_results() -> None:
    results = _sarif(fixture_path("clean_catalog.json"))["runs"][0]["results"]
    assert results, "a clean run still lists what it did not check"
    assert {r["kind"] for r in results} == {"open"}
    assert all(r["level"] == "note" for r in results)


def test_a_broken_document_renders_its_errors_as_failures() -> None:
    results = _sarif(fixture_path("broken_catalog.json"))["runs"][0]["results"]
    failures = [r for r in results if r["kind"] == "fail"]
    assert len(failures) == 3
    assert all(r["level"] == "error" for r in failures)
    assert all(r["properties"]["severity"] == "ERROR" for r in failures)


def test_an_info_finding_is_informational_and_still_shown() -> None:
    results = _sarif(fixture_path("clean_profile.json"), [fixture_path("clean_catalog.json")])[
        "runs"
    ][0]["results"]
    resolved = [r for r in results if r["ruleId"] == "IMPORT_RESOLVED"]
    assert resolved
    assert all(r["kind"] == "informational" and r["level"] == "note" for r in resolved)


# -- rules: one per code, every source named, nothing invented ----------------


def test_every_result_points_at_a_rule_that_names_its_sources() -> None:
    log = _sarif(fixture_path("broken_catalog.json"))
    rules = log["runs"][0]["tool"]["driver"]["rules"]
    ids = [rule["id"] for rule in rules]
    assert ids == sorted(ids) and len(ids) == len(set(ids))
    for result in log["runs"][0]["results"]:
        rule = rules[result["ruleIndex"]]
        assert rule["id"] == result["ruleId"]
        cited = result["properties"]["rule"]
        assert {"url": cited["url"], "retrieved": cited["retrieved"]} in rule["properties"][
            "sources"
        ]
        assert rule["shortDescription"]["text"]


def test_help_uri_is_the_citation_url_and_only_when_it_is_a_url() -> None:
    rules = _sarif(fixture_path("broken_catalog.json"))["runs"][0]["tool"]["driver"]["rules"]
    by_id = {rule["id"]: rule for rule in rules}
    schema_rule = by_id["REQUIRED_PROPERTY_MISSING"]
    assert schema_rule["helpUri"].startswith("https://github.com/usnistgov/OSCAL/")
    # Tool policy cites the README, which is not a URI; no helpUri is invented.
    policy = by_id["PATTERN_NOT_CHECKED"]
    assert "helpUri" not in policy
    assert policy["properties"]["sources"] == [{"url": "README.md (Limits)", "retrieved": "-"}]


def test_a_code_cited_from_two_sources_keeps_both_and_no_single_help_uri() -> None:
    """REFERENCE_UNRESOLVED cites the constraint layer or the prose rule.

    When one report carries both, the rule names both sources, with their
    dates, and picks neither as ``helpUri``: a single link would misattribute
    half the findings.
    """
    layer = Rule(citation="NIST OSCAL constraint x", url="https://a.example/x.xml", retrieved="d1")
    prose = Rule(citation="NIST prose", url="https://b.example/page/", retrieved="d2")
    findings = [
        Finding("REFERENCE_UNRESOLVED", Severity.ERROR, "/catalog/a", "href", "#x", "m", layer),
        Finding("REFERENCE_UNRESOLVED", Severity.ERROR, "/catalog/b", "href", "#y", "m", prose),
        Finding("UUID_NOT_UNIQUE", Severity.ERROR, "/catalog/c", "uuid", "u", "m", prose),
    ]
    log = json.loads(render_findings_sarif(findings, __version__, "catalog", Path("doc.json")))
    by_id = {rule["id"]: rule for rule in log["runs"][0]["tool"]["driver"]["rules"]}
    assert "helpUri" not in by_id["REFERENCE_UNRESOLVED"]
    assert by_id["REFERENCE_UNRESOLVED"]["properties"]["sources"] == [
        {"url": "https://a.example/x.xml", "retrieved": "d1"},
        {"url": "https://b.example/page/", "retrieved": "d2"},
    ]
    assert by_id["UUID_NOT_UNIQUE"]["helpUri"] == "https://b.example/page/"
    assert [r["ruleIndex"] for r in log["runs"][0]["results"]] == [0, 0, 1]
    errors = list(Draft4Validator(SCHEMA).iter_errors(log))
    assert not errors, errors


def test_every_code_the_checks_can_emit_has_a_description() -> None:
    # A code is assigned on one line, as ``code="X"``, ``code = "X"``, or
    # ``code="X" if ... else "Y"``; every quoted token on such a line is one.
    emitted: set[str] = set()
    for path in CHECKS.glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search(r"\bcode\s*=", line):
                emitted |= set(re.findall(r'"([A-Z][A-Z_]+)"', line))
    assert len(emitted) >= 19, sorted(emitted)
    assert emitted == set(DESCRIPTIONS), sorted(emitted ^ set(DESCRIPTIONS))


# -- locations: the pointer, never an invented line ----------------------------


def test_locations_carry_the_document_and_the_json_pointer_and_no_line() -> None:
    document = fixture_path("broken_catalog.json")
    for result in _sarif(document)["runs"][0]["results"]:
        [location] = result["locations"]
        physical = location["physicalLocation"]
        assert physical["artifactLocation"]["uri"] == document.as_uri()
        assert "region" not in physical
        [logical] = location["logicalLocations"]
        assert logical["fullyQualifiedName"] == result["properties"]["location"]
        assert logical["fullyQualifiedName"].startswith("/catalog")


def test_a_relative_document_path_is_kept_relative() -> None:
    log = json.loads(run("tests/fixtures/clean_catalog.json").split(b"\n[exit")[0])
    uris = {
        r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        for r in log["runs"][0]["results"]
    }
    assert uris == {"tests/fixtures/clean_catalog.json"}


def test_a_finding_in_a_supporting_document_is_located_in_that_document(
    tmp_path: Path,
) -> None:
    """A profile importing a profile importing a catalog.

    The middle profile's own import is resolved, and that finding lives in
    the middle file: its SARIF location names that file, not the primary.
    """
    middle = write(tmp_path, "clean_profile.json", load_fixture("clean_profile.json"))
    write(tmp_path, "clean_catalog.json", load_fixture("clean_catalog.json"))
    top = {
        "profile": {
            "uuid": "9c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
            "metadata": {
                "title": "Synthetic Top Profile",
                "last-modified": "2026-08-14T00:00:00Z",
                "version": "1.0.0",
                "oscal-version": "1.2.3",
            },
            "imports": [
                {"href": "clean_profile.json", "include-controls": [{"with-ids": ["ex-1"]}]}
            ],
        }
    }
    document = write(tmp_path, "top.json", top)
    results = _sarif(document, [tmp_path])["runs"][0]["results"]
    elsewhere = [
        r
        for r in results
        if r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] != document.as_uri()
    ]
    assert elsewhere, "expected a finding located in the supporting profile"
    for result in elsewhere:
        physical = result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        assert physical == middle.as_uri()
        pointer = result["locations"][0]["logicalLocations"][0]["fullyQualifiedName"]
        assert pointer.startswith("/profile/")
        assert result["properties"]["location"] == f"{middle}#{pointer}"


def test_location_splitting_tells_a_pointer_from_a_path() -> None:
    assert _split_location("/catalog/metadata", "catalog") == (None, "/catalog/metadata")
    assert _split_location("/catalog", "catalog") == (None, "/catalog")
    assert _split_location("/abs/dir/cat.json#/catalog/uuid", "profile") == (
        "/abs/dir/cat.json",
        "/catalog/uuid",
    )
    assert _split_location("rel/cat.json#/catalog", "profile") == ("rel/cat.json", "/catalog")
    # A pointer into the primary that happens to contain '#' is still a pointer.
    assert _split_location("/catalog/metadata/x#/y", "catalog") == (
        None,
        "/catalog/metadata/x#/y",
    )


def test_fingerprints_are_stable_and_distinct() -> None:
    first = _sarif(fixture_path("broken_catalog.json"))["runs"][0]["results"]
    second = _sarif(fixture_path("broken_catalog.json"))["runs"][0]["results"]
    prints = [r["partialFingerprints"][FINGERPRINT] for r in first]
    assert prints == [r["partialFingerprints"][FINGERPRINT] for r in second]
    assert len(set(prints)) == len(prints)


# -- the CLI --------------------------------------------------------------------


def test_the_cli_exit_code_is_the_same_as_for_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(fixture_path("broken_catalog.json")), "--format", "sarif"]) == 1
    log = json.loads(capsys.readouterr().out)
    assert log["version"] == "2.1.0"
    assert main([str(fixture_path("clean_catalog.json")), "--format", "sarif"]) == 0
    assert json.loads(capsys.readouterr().out)["runs"][0]["properties"]["summary"]["ERROR"] == 0


def test_the_report_carries_no_timestamp() -> None:
    rendered = json.dumps(_sarif(fixture_path("clean_catalog.json")))
    for word in ("timestamp", "startTimeUtc", "endTimeUtc", "generated_at", "duration"):
        assert word not in rendered
