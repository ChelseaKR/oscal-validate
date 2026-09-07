"""``--format sarif``: the same findings, in SARIF 2.1.0, with no pass invented.

Three things are pinned here. The output validates against the vendored
OASIS schema, offline. It carries exactly the findings the canonical JSON
report carries, in the same order, with the same citation on each. And the
severity mapping never produces ``kind: pass``: an UNVERIFIABLE finding is
``open``, and a report's results are never empty.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft4Validator

from oscal_validate import __version__, snapshot, validate_file
from oscal_validate.cli import main
from oscal_validate.findings import Finding, Rule, Severity, render_findings_json
from oscal_validate.rules import OSCAL_RELEASE
from oscal_validate.sarif import (
    DESCRIPTIONS,
    FINGERPRINT,
    KINDS,
    _split_location,
    merge_logs,
    render_findings_sarif,
)
from oscal_validate.snapshot import VENDORED_FILES, digests
from oscal_validate.validator import build_session, validate

from . import test_vendor_integrity
from .conftest import fixture_path, load_fixture, write
from .sarif.capture import CASES, HERE, ROOT, run

EXPECTED_VENDOR_HASHES = test_vendor_integrity.EXPECTED

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


def test_the_run_names_the_document_it_is_about() -> None:
    document = fixture_path("broken_catalog.json")
    document_properties = _sarif(document)["runs"][0]["properties"]["document"]
    assert document_properties == {"model": "catalog", "path": document.as_uri()}


# -- which bytes decided it -----------------------------------------------------


def test_the_driver_records_the_release_and_a_digest_of_every_vendored_file() -> None:
    driver = _sarif(fixture_path("clean_catalog.json"))["runs"][0]["tool"]["driver"]
    recorded = driver["properties"]["vendoredSnapshot"]
    assert recorded["release"] == OSCAL_RELEASE
    assert recorded["algorithm"] == "sha256"
    assert set(recorded["files"]) == set(VENDORED_FILES)
    for digest in recorded["files"].values():
        assert re.fullmatch(r"[0-9a-f]{64}", digest)


def test_the_driver_digests_are_the_hashes_the_integrity_gate_records() -> None:
    """The digests are computed from the files; these are transcribed from
    SOURCES.md. They are two independent answers to "which snapshot is this",
    and the whole value of shipping the first one is that it can disagree with
    the second."""
    recorded = _sarif(fixture_path("clean_catalog.json"))["runs"][0]["tool"]["driver"][
        "properties"
    ]["vendoredSnapshot"]["files"]
    assert recorded == EXPECTED_VENDOR_HASHES


def test_the_snapshot_identity_covers_every_vendored_file() -> None:
    """A partial fingerprint is the worse failure: it looks complete while a
    changed metaschema module passes under it."""
    vendored = ROOT / "src" / "oscal_validate" / "vendor"
    on_disk = {
        str(path.relative_to(vendored).as_posix())
        for path in vendored.rglob("*")
        if path.is_file() and path.name != "SOURCES.md"
    }
    assert on_disk == set(VENDORED_FILES)


def test_the_digests_are_taken_from_the_bytes_and_not_from_a_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Alter one vendored file's bytes and the digest must move with them. A
    digest transcribed from SOURCES.md would sit still and keep vouching for
    a snapshot the tool is no longer reading."""
    schema = VENDORED_FILES[0]
    vendor = ROOT / "src" / "oscal_validate" / "vendor"
    real = (vendor / schema).read_bytes()

    def altered(relpath: str) -> bytes:
        data = (vendor / relpath).read_bytes()
        return data + b"\n" if relpath == schema else data

    digests.cache_clear()
    try:
        monkeypatch.setattr(snapshot, "_read", altered)
        moved = digests()[schema]
    finally:
        digests.cache_clear()
        monkeypatch.undo()
    assert moved == hashlib.sha256(real + b"\n").hexdigest()
    assert moved != EXPECTED_VENDOR_HASHES[schema]
    assert digests()[schema] == EXPECTED_VENDOR_HASHES[schema]


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


# -- merging: one file for a delivery of many documents -------------------------


def _log(document: Path, resolve: list[Path] | None = None) -> dict[str, Any]:
    return _sarif(document, resolve)


def test_a_merged_log_validates_against_the_sarif_schema() -> None:
    merged = json.loads(
        merge_logs(
            [_log(fixture_path("broken_catalog.json")), _log(fixture_path("clean_profile.json"))]
        )
    )
    Draft4Validator(SCHEMA).validate(merged)
    assert len(merged["runs"]) == 1


def test_merging_keeps_every_result_and_sums_every_summary() -> None:
    first = _log(fixture_path("broken_catalog.json"))
    second = _log(fixture_path("clean_profile.json"))
    merged = json.loads(merge_logs([first, second]))
    run = merged["runs"][0]
    assert len(run["results"]) == len(first["runs"][0]["results"]) + len(
        second["runs"][0]["results"]
    )
    for severity, total in run["properties"]["summary"].items():
        assert total == (
            first["runs"][0]["properties"]["summary"][severity]
            + second["runs"][0]["properties"]["summary"][severity]
        )
    assert run["properties"]["documents"] == [
        first["runs"][0]["properties"]["document"],
        second["runs"][0]["properties"]["document"],
    ]


def test_every_merged_result_still_points_at_its_own_rule() -> None:
    """Re-indexing is the one thing a merge can get quietly wrong: a
    ruleIndex off by one attributes a finding to another rule's citation."""
    merged = json.loads(
        merge_logs(
            [_log(fixture_path("broken_catalog.json")), _log(fixture_path("clean_profile.json"))]
        )
    )
    run = merged["runs"][0]
    rules = run["tool"]["driver"]["rules"]
    assert rules, "a merged log with results must carry the rules they cite"
    for result in run["results"]:
        assert rules[result["ruleIndex"]]["id"] == result["ruleId"]


def test_a_merged_rule_keeps_every_source_both_documents_cited() -> None:
    first = _log(fixture_path("broken_catalog.json"))
    second = _log(fixture_path("clean_profile.json"))
    merged = json.loads(merge_logs([first, second]))
    sources: dict[str, set[tuple[str, str]]] = {}
    for log in (first, second):
        for rule in log["runs"][0]["tool"]["driver"]["rules"]:
            cited = sources.setdefault(rule["id"], set())
            for source in rule["properties"]["sources"]:
                cited.add((source["url"], source["retrieved"]))
    for rule in merged["runs"][0]["tool"]["driver"]["rules"]:
        got = {(s["url"], s["retrieved"]) for s in rule["properties"]["sources"]}
        assert got == sources[rule["id"]]
        urls = {url for url, _ in got}
        expected = len(urls) == 1 and next(iter(urls)).startswith("https://")
        assert ("helpUri" in rule) == expected


def test_merging_one_log_is_that_log_with_its_document_listed() -> None:
    only = _log(fixture_path("broken_catalog.json"))
    merged = json.loads(merge_logs([only]))
    assert merged["runs"][0]["results"] == only["runs"][0]["results"]
    assert merged["runs"][0]["tool"]["driver"] == only["runs"][0]["tool"]["driver"]


def test_merging_across_two_snapshots_is_refused_rather_than_attributed() -> None:
    """Two logs from different vendored snapshots describe two different
    OSCAL releases. Merging them silently would file one snapshot's verdicts
    under the other's digests."""
    first = _log(fixture_path("broken_catalog.json"))
    second = copy.deepcopy(first)
    files = second["runs"][0]["tool"]["driver"]["properties"]["vendoredSnapshot"]["files"]
    files[VENDORED_FILES[0]] = "0" * 64
    with pytest.raises(ValueError, match="one vendored snapshot"):
        merge_logs([first, second])


def test_merging_refuses_a_log_that_is_not_a_single_sarif_2_1_0_run() -> None:
    good = _log(fixture_path("broken_catalog.json"))
    with pytest.raises(ValueError, match="no logs to merge"):
        merge_logs([])
    with pytest.raises(ValueError, match="SARIF 2.1.0"):
        merge_logs([{**good, "version": "2.0.0"}])
    with pytest.raises(ValueError, match="exactly one run"):
        merge_logs([{**good, "runs": good["runs"] + good["runs"]}])
    with pytest.raises(ValueError, match="SARIF 2.1.0"):
        merge_logs(["not a log"])
