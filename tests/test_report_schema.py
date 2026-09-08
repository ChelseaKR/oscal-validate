"""The JSON report has a published shape, and the suite holds it to it.

Until this file existed, the shape of ``--format json`` was whatever
``render_findings_json`` happened to write. Three consumers parse it -- the
GitHub Action, the survey harness, and anything wiring the tool into a
pipeline -- and one of them, the Action, read its counts with
``summary.get(severity, 0)``: a key that went missing counted as zero findings
and the gate passed. An absence published as a measurement, in the tool whose
purpose is to refuse exactly that.

So: ``report.schema.json`` is shipped as package data, ``--report-schema``
prints it, every report carries ``report_schema_version``, and everything
below either validates a real report against that schema or breaks the
contract on purpose and checks that something notices.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from oscal_validate import (
    REPORT_SCHEMA_VERSION,
    Finding,
    Rule,
    Severity,
    read_report_schema,
    validate_file,
)
from oscal_validate import __version__ as tool_version
from oscal_validate.findings import render_findings_json
from oscal_validate.report import REPORT_SCHEMA_PATH
from oscal_validate.suggest import Suggestion

from .conftest import fixture_path
from .schema_check import UnsupportedKeyword, check

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden"
SCHEMA: dict[str, Any] = json.loads(read_report_schema())

#: Fixtures whose live reports are validated. Between them they carry every
#: severity the tool emits, both location forms, and a report with ERRORs.
DOCUMENTS = [
    ("clean_catalog.json", []),
    ("broken_catalog.json", []),
    ("clean_profile.json", []),
    ("clean_profile.json", ["clean_catalog.json"]),
    ("nist_ssp_example.json", []),
]


def _report(document: str, resolve: list[str]) -> dict[str, Any]:
    findings = validate_file(fixture_path(document), [fixture_path(r) for r in resolve])
    report: dict[str, Any] = json.loads(render_findings_json(findings, tool_version, "catalog"))
    return report


# -- the schema is published, and it is what the report says it is -------------


def test_the_schema_ships_as_package_data() -> None:
    listed = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"report.schema.json"' in listed, "package-data no longer ships the schema"
    assert REPORT_SCHEMA_PATH.is_file()


def test_the_report_schema_flag_prints_the_shipped_schema_and_exits_clean() -> None:
    command = [sys.executable, "-m", "oscal_validate", "--report-schema"]
    runs = [subprocess.run(command, capture_output=True, check=False) for _ in range(2)]
    assert runs[0].returncode == 0
    assert runs[0].stdout == runs[1].stdout
    assert runs[0].stdout.decode("utf-8") == REPORT_SCHEMA_PATH.read_text(encoding="utf-8")
    assert json.loads(runs[0].stdout)["$schema"].endswith("/2020-12/schema")


def test_the_schemas_declared_version_is_the_one_reports_carry() -> None:
    assert SCHEMA["properties"]["report_schema_version"]["const"] == REPORT_SCHEMA_VERSION
    assert REPORT_SCHEMA_VERSION.count(".") == 2


def test_every_report_declares_the_schema_version_and_the_tool_version() -> None:
    report = _report("broken_catalog.json", [])
    assert report["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert report["tool"] == {"name": "oscal-validate", "version": tool_version}
    assert report["report_schema_version"] != report["tool"]["version"], (
        "the two versions must be able to move independently"
    )


# -- every report the suite can produce conforms -------------------------------


@pytest.mark.parametrize(("document", "resolve"), DOCUMENTS)
def test_a_live_report_validates_against_the_shipped_schema(
    document: str, resolve: list[str]
) -> None:
    assert check(_report(document, resolve), SCHEMA) == []


def test_every_committed_golden_report_validates_against_the_shipped_schema() -> None:
    goldens = sorted(GOLDEN.glob("*.json.out"))
    assert len(goldens) >= 12, "the golden set shrank; the schema gate shrank with it"
    for golden in goldens:
        body = golden.read_text(encoding="utf-8").rsplit("\n[exit ", 1)[0]
        assert check(json.loads(body), SCHEMA) == [], golden.name


def test_a_report_with_suggestions_validates_too() -> None:
    """``--suggest`` adds a key to a finding, and the schema declares it."""
    findings = validate_file(
        fixture_path("clean_profile.json"), [fixture_path("clean_catalog.json")], suggest=True
    )
    report = json.loads(render_findings_json(findings, tool_version, "profile"))
    assert check(report, SCHEMA) == []
    rule = Rule(citation="c", url="https://example.invalid/", retrieved="2026-01-01")
    with_suggestion = json.loads(
        render_findings_json(
            [
                Finding(
                    "REFERENCE_UNRESOLVED",
                    Severity.ERROR,
                    "/catalog/a",
                    "href",
                    "#x",
                    "m",
                    rule,
                    suggestions=(Suggestion("#y", "case"),),
                )
            ],
            tool_version,
            "catalog",
        )
    )
    assert with_suggestion["findings"][0]["suggestions"] == [{"value": "#y", "difference": "case"}]
    assert check(with_suggestion, SCHEMA) == []


# -- break the contract on purpose ---------------------------------------------


def _valid() -> dict[str, Any]:
    return _report("broken_catalog.json", [])


def test_renaming_summary_is_caught_before_it_reaches_a_consumer() -> None:
    report = _valid()
    report["totals"] = report.pop("summary")
    errors = check(report, SCHEMA)
    assert any("summary" in e for e in errors), errors
    assert any("totals" in e for e in errors), errors


def test_a_summary_missing_one_severity_is_caught() -> None:
    report = _valid()
    del report["summary"]["UNVERIFIABLE"]
    assert check(report, SCHEMA) != []


def test_a_count_that_is_not_a_number_is_caught() -> None:
    report = _valid()
    report["summary"]["ERROR"] = "3"
    assert check(report, SCHEMA) != []


def test_a_negative_count_is_caught() -> None:
    report = _valid()
    report["summary"]["ERROR"] = -1
    assert check(report, SCHEMA) != []


def test_an_unknown_severity_is_caught() -> None:
    report = _valid()
    report["findings"][0]["severity"] = "CRITICAL"
    assert check(report, SCHEMA) != []


def test_a_finding_that_lost_its_rule_is_caught() -> None:
    report = _valid()
    del report["findings"][0]["rule"]
    assert check(report, SCHEMA) != []


def test_a_finding_that_lost_its_retrieval_date_is_caught() -> None:
    report = _valid()
    del report["findings"][0]["rule"]["retrieved"]
    assert check(report, SCHEMA) != []


def test_a_new_undeclared_key_is_caught_rather_than_ignored() -> None:
    report = _valid()
    report["findings"][0]["confidence"] = 0.9
    assert check(report, SCHEMA) != []


def test_a_report_declaring_the_wrong_schema_version_is_caught() -> None:
    report = _valid()
    report["report_schema_version"] = "2.0.0"
    assert check(report, SCHEMA) != []


def test_a_report_with_no_schema_version_at_all_is_caught() -> None:
    report = _valid()
    del report["report_schema_version"]
    assert check(report, SCHEMA) != []


# -- the checker itself cannot pass by ignoring --------------------------------


def test_the_checker_refuses_a_keyword_it_does_not_enforce() -> None:
    """A subset checker that skipped unknown keywords would be a gate that
    cannot fail on the half of the contract it does not implement."""
    with pytest.raises(UnsupportedKeyword):
        check({"a": 1}, {"type": "object", "patternProperties": {"^a$": {"type": "string"}}})


def test_the_checker_enforces_every_keyword_the_shipped_schema_uses() -> None:
    """Walking the real schema must raise nothing: every keyword in it is
    implemented above, which is what makes the conformance tests mean
    something."""
    assert check(_valid(), SCHEMA) == []
    assert check({}, SCHEMA) != []


def test_the_checker_does_not_confuse_a_boolean_with_an_integer() -> None:
    assert check(True, {"type": "integer"}) != []
    assert check(1, {"type": "integer"}) == []


def test_the_checker_reads_local_references() -> None:
    schema = {
        "type": "object",
        "properties": {"n": {"$ref": "#/$defs/count"}},
        "$defs": {"count": {"type": "integer", "minimum": 0}},
    }
    assert check({"n": 1}, schema) == []
    assert check({"n": -1}, schema) != []


# -- the schema and the renderer cannot drift apart ----------------------------


def test_every_key_the_renderer_writes_is_declared_by_the_schema() -> None:
    """The schema sets additionalProperties false everywhere, so a key added
    to the renderer and not to the schema fails here rather than reaching a
    consumer that would silently ignore it."""
    report = _valid()
    declared = set(SCHEMA["properties"])
    # Every key the renderer writes is declared, and every key the schema
    # *requires* is written. `baseline` is declared and optional, so equality
    # would fail on a run that was given no baseline -- which is the run this
    # fixture is. The pair of assertions below is what equality was standing in
    # for, and it stays exact in both directions.
    assert set(report) <= declared, set(report) - declared
    assert set(SCHEMA["required"]) <= set(report), set(SCHEMA["required"]) - set(report)
    optional = declared - set(SCHEMA["required"])
    assert optional == {"baseline"}, "a new optional key needs a case here that writes it"
    with_baseline = json.loads(
        render_findings_json(
            validate_file(fixture_path("broken_catalog.json")),
            tool_version,
            "catalog",
            "oscal-baseline.json",
        )
    )
    assert set(with_baseline) == declared
    assert check(with_baseline, SCHEMA) == []
    finding_properties = set(SCHEMA["$defs"]["finding"]["properties"])
    for finding in report["findings"]:
        assert set(finding) <= finding_properties, set(finding) - finding_properties


def test_the_schema_declares_the_severities_the_tool_actually_has() -> None:
    assert SCHEMA["$defs"]["severity"]["enum"] == [s.value for s in Severity]
    assert set(SCHEMA["properties"]["summary"]["required"]) == {s.value for s in Severity}


def test_the_shipped_schema_is_byte_stable() -> None:
    """It is package data and a published artifact; a reformatting pass that
    changed its bytes without changing its version would be invisible."""
    raw = REPORT_SCHEMA_PATH.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert json.dumps(json.loads(raw), indent=2, ensure_ascii=False) + "\n" == raw


def test_a_deep_copy_of_a_report_is_still_a_report() -> None:
    assert check(copy.deepcopy(_valid()), SCHEMA) == []
