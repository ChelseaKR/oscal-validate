"""The published findings must agree with the evidence beside them.

A findings document that drifts from its own data is worse than no findings
document, so the numbers in the write-up are recomputed from the survey JSON
rather than trusted. The same tests guard the two things a survey run could get
wrong on its way into the repository: a malformed target list, and document
content leaking into the committed evidence.

There are two runs, and the second one's whole point is the difference between
them, so the delta table is recomputed from both JSONs rather than typed in.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "tools" / "survey-urls.txt"
FINDINGS = ROOT / "docs" / "findings"

WITHHELD = FINDINGS / "2026-08-14-published-oscal-survey.json"
WITHHELD_WRITEUP = FINDINGS / "2026-08-14-published-oscal-survey.md"
SUPPLIED = FINDINGS / "2026-08-15-imports-supplied-survey.json"
SUPPLIED_WRITEUP = FINDINGS / "2026-08-15-imports-supplied-survey.md"

PAIRS = [(WITHHELD, WITHHELD_WRITEUP), (SUPPLIED, SUPPLIED_WRITEUP)]

#: Everything a survey record is allowed to carry. The survey reports on whether
#: published documents conform, so it records codes, counts, and JSON Pointers;
#: a record holding a value read from someone's document would mean this
#: repository had quietly become a copy of their content. ``resolve`` is a list
#: of URLs from this repository's own target list, not a value read from anyone.
RECORD_KEYS = {
    "bytes",
    "codes",
    "effective_model_complete",
    "example_location",
    "fetch",
    "group",
    "imports",
    "imports_resolved",
    "model",
    "outcome",
    "reason",
    "resolve",
    "summary",
    "url",
}

SUPPORTING_KEYS = {"bytes", "fetch", "outcome", "url"}


def _payload(survey: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(survey.read_text(encoding="utf-8"))
    return data


def _records(survey: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = _payload(survey)["records"]
    return records


def _totals(survey: Path) -> Counter[str]:
    totals: Counter[str] = Counter()
    for record in _records(survey):
        totals.update(record.get("codes", {}))
    return totals


def _headline(writeup: Path) -> dict[str, int]:
    """Label -> count, from the write-up's first table."""
    found: dict[str, int] = {}
    for line in writeup.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) >= 4 and re.fullmatch(r"\d+", cells[2]):
            found.setdefault(cells[1], int(cells[2]))
    return found


def _target_lines() -> list[list[str]]:
    return [
        line.split("\t")
        for line in TARGETS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _targets() -> list[str]:
    return [parts[1] for parts in _target_lines()]


def test_the_target_list_is_well_formed() -> None:
    for line in TARGETS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        assert len(parts) in (2, 3), f"expected group<TAB>url[<TAB>resolve]: {line!r}"
        assert parts[0].strip() and not parts[0].startswith(" ")
        assert parts[1].startswith("https://"), parts[1]
        for resolve in parts[2].split(",") if len(parts) > 2 else []:
            assert resolve.startswith("https://"), resolve
            assert resolve != parts[1], f"a document cannot resolve against itself: {resolve}"
    urls = _targets()
    assert len(set(urls)) == len(urls), "a duplicate URL would double-count a document"


@pytest.mark.parametrize("survey", [WITHHELD, SUPPLIED])
def test_every_target_appears_in_the_survey_exactly_once(survey: Path) -> None:
    assert [record["url"] for record in _records(survey)] == _targets()


@pytest.mark.parametrize("survey", [WITHHELD, SUPPLIED])
def test_the_evidence_carries_no_document_content(survey: Path) -> None:
    for record in _records(survey):
        unexpected = set(record) - RECORD_KEYS
        assert not unexpected, f"{record['url']}: unexpected keys {sorted(unexpected)}"
    for entry in _payload(survey).get("supporting", []):
        unexpected = set(entry) - SUPPORTING_KEYS
        assert not unexpected, f"{entry['url']}: unexpected keys {sorted(unexpected)}"


@pytest.mark.parametrize(("survey", "writeup"), PAIRS)
def test_the_headline_numbers_match_the_evidence(survey: Path, writeup: Path) -> None:
    records = _records(survey)
    validated = [r for r in records if "summary" in r]
    complete = sum(1 for r in validated if r["effective_model_complete"])
    expected = {
        "Documents attempted": len(records),
        "Documents validated": len(validated),
        "Blocked by robots.txt": sum(1 for r in records if r["outcome"] == "blocked by robots.txt"),
        "Carried at least one ERROR finding": sum(1 for r in validated if r["summary"]["ERROR"]),
        "Had a complete effective data model (every import supplied)": complete,
        f"Of those {complete}, carried at least one ERROR": sum(
            1 for r in validated if r["effective_model_complete"] and r["summary"]["ERROR"]
        ),
    }
    headline = _headline(writeup)
    for label, count in expected.items():
        assert headline.get(label) == count, label


@pytest.mark.parametrize(("survey", "writeup"), PAIRS)
def test_the_finding_totals_match_the_evidence(survey: Path, writeup: Path) -> None:
    totals = _totals(survey)
    text = writeup.read_text(encoding="utf-8")
    for code in ("REFERENCE_UNRESOLVED", "UUID_NOT_UNIQUE", "CONSTRAINT_CARDINALITY"):
        assert f"| `{code}` | ERROR | {totals[code]} |" in text, code
    assert f"{totals['REFERENCE_UNVERIFIABLE']:,}" in text


@pytest.mark.parametrize(("survey", "writeup"), PAIRS)
def test_every_document_the_writeup_names_as_failing_did_fail(survey: Path, writeup: Path) -> None:
    text = writeup.read_text(encoding="utf-8")
    for record in _records(survey):
        name = record["url"].rsplit("/", 1)[-1]
        if record.get("summary", {}).get("ERROR"):
            assert name in text, f"{name} carried ERRORs and is not named in the write-up"


@pytest.mark.parametrize("writeup", [WITHHELD_WRITEUP, SUPPLIED_WRITEUP])
def test_the_writeup_never_claims_conformance_from_a_clean_run(writeup: Path) -> None:
    text = writeup.read_text(encoding="utf-8")
    assert "has not been shown to conform" in text
    assert "No percentage here is a population estimate" in text.replace("\n", " ")


# -- the second run, whose subject is the difference ------------------------


def test_the_supplied_run_used_exactly_the_resolve_column() -> None:
    declared = {
        parts[1]: parts[2].split(",") if len(parts) > 2 else [] for parts in _target_lines()
    }
    for record in _records(SUPPLIED):
        assert record["resolve"] == declared[record["url"]], record["url"]


def test_the_withheld_run_supplied_only_what_its_own_column_declared() -> None:
    """The 2026-08-14 evidence predates the resolve column being filled in.

    Its records carry no ``resolve`` key at all, and the delta below is only
    meaningful if that run really did withhold what this one supplies.
    """
    supplied_edges = sum(r.get("imports_resolved", 0) for r in _records(SUPPLIED))
    withheld_edges = sum(r.get("imports_resolved", 0) for r in _records(WITHHELD))
    assert withheld_edges < supplied_edges


def test_every_supporting_document_is_named_by_some_target() -> None:
    named = {url for parts in _target_lines() if len(parts) > 2 for url in parts[2].split(",")}
    listed = {entry["url"] for entry in _payload(SUPPLIED)["supporting"]}
    assert listed == named


def test_the_delta_table_is_the_difference_between_the_two_runs() -> None:
    """Every row of the write-up's delta table, recomputed from both JSONs."""
    before, after = _totals(WITHHELD), _totals(SUPPLIED)
    text = SUPPLIED_WRITEUP.read_text(encoding="utf-8")
    codes = sorted(set(before) | set(after))
    assert codes, "no finding codes in either run"
    for code in codes:
        change = after[code] - before[code]
        row = (
            f"| `{code}` | {before[code]:,} | {after[code]:,} | "
            f"{'+' if change > 0 else ''}{change:,} |"
        )
        assert row in text, f"delta row missing or wrong for {code}: expected {row!r}"


def test_the_settled_split_adds_up() -> None:
    """The headline claim: what happened to each unsettled reference.

    Every ``REFERENCE_UNVERIFIABLE`` from the first run either became an ERROR,
    resolved cleanly, or stayed unsettled. Nothing else can have happened to
    it, and the three numbers in the write-up must therefore sum to the first
    run's total.
    """
    before, after = _totals(WITHHELD), _totals(SUPPLIED)
    unsettled_before = before["REFERENCE_UNVERIFIABLE"]
    still_unsettled = after["REFERENCE_UNVERIFIABLE"]
    became_errors = after["REFERENCE_UNRESOLVED"] - before["REFERENCE_UNRESOLVED"]
    resolved_clean = unsettled_before - still_unsettled - became_errors
    assert became_errors >= 0 and resolved_clean >= 0
    text = SUPPLIED_WRITEUP.read_text(encoding="utf-8")
    for label, value in (
        ("resolved to something that exists", resolved_clean),
        ("resolved to nothing, and are now ERROR", became_errors),
        ("still cannot be settled", still_unsettled),
    ):
        assert f"| {label} | {value:,} |" in text, f"{label} should be {value:,}"


def test_the_documents_that_stayed_unsettled_are_all_named() -> None:
    text = SUPPLIED_WRITEUP.read_text(encoding="utf-8")
    incomplete = [r for r in _records(SUPPLIED) if not r.get("effective_model_complete", True)]
    assert incomplete, "the whole point is that some documents could not be completed"
    for record in incomplete:
        name = record["url"].rsplit("/", 1)[-1]
        assert name in text, f"{name} stayed incomplete and is not named in the write-up"
