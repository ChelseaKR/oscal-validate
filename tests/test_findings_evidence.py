"""The published findings must agree with the evidence beside them.

A findings document that drifts from its own data is worse than no findings
document, so the numbers in the write-up are recomputed from the survey JSON
rather than trusted. The same tests guard the two things a survey run could get
wrong on its way into the repository: a malformed target list, and document
content leaking into the committed evidence.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "tools" / "survey-urls.txt"
SURVEY = ROOT / "docs" / "findings" / "2026-08-14-published-oscal-survey.json"
WRITEUP = ROOT / "docs" / "findings" / "2026-08-14-published-oscal-survey.md"

#: Everything a survey record is allowed to carry. The survey reports on whether
#: published documents conform, so it records codes, counts, and JSON Pointers;
#: a record holding a value read from someone's document would mean this
#: repository had quietly become a copy of their content.
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
    "summary",
    "url",
}


def _payload() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(SURVEY.read_text(encoding="utf-8"))
    return data


def _records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = _payload()["records"]
    return records


def _headline() -> dict[str, int]:
    """Label -> count, from the write-up's first table."""
    found: dict[str, int] = {}
    for line in WRITEUP.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) >= 4 and re.fullmatch(r"\d+", cells[2]):
            found[cells[1]] = int(cells[2])
    return found


def _targets() -> list[str]:
    return [
        line.split("\t")[1]
        for line in TARGETS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def test_the_target_list_is_well_formed() -> None:
    for line in TARGETS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        assert len(parts) in (2, 3), f"expected group<TAB>url[<TAB>resolve]: {line!r}"
        assert parts[0].strip() and not parts[0].startswith(" ")
        assert parts[1].startswith("https://"), parts[1]
    urls = _targets()
    assert len(set(urls)) == len(urls), "a duplicate URL would double-count a document"


def test_every_target_appears_in_the_survey_exactly_once() -> None:
    assert [record["url"] for record in _records()] == _targets()


def test_the_evidence_carries_no_document_content() -> None:
    for record in _records():
        unexpected = set(record) - RECORD_KEYS
        assert not unexpected, f"{record['url']}: unexpected keys {sorted(unexpected)}"


def test_the_headline_numbers_match_the_evidence() -> None:
    records = _records()
    validated = [r for r in records if "summary" in r]
    expected = {
        "Documents attempted": len(records),
        "Documents validated": len(validated),
        "Blocked by robots.txt": sum(1 for r in records if r["outcome"] == "blocked by robots.txt"),
        "Carried at least one ERROR finding": sum(1 for r in validated if r["summary"]["ERROR"]),
        "Had a complete effective data model (every import supplied)": sum(
            1 for r in validated if r["effective_model_complete"]
        ),
        "Of those 22, carried at least one ERROR": sum(
            1 for r in validated if r["effective_model_complete"] and r["summary"]["ERROR"]
        ),
    }
    headline = _headline()
    for label, count in expected.items():
        assert headline.get(label) == count, label


def test_the_finding_totals_match_the_evidence() -> None:
    totals: Counter[str] = Counter()
    for record in _records():
        totals.update(record.get("codes", {}))
    text = WRITEUP.read_text(encoding="utf-8")
    for code in ("REFERENCE_UNRESOLVED", "UUID_NOT_UNIQUE", "CONSTRAINT_CARDINALITY"):
        assert f"| `{code}` | ERROR | {totals[code]} |" in text, code
    assert f"{totals['REFERENCE_UNVERIFIABLE']:,}" in text


def test_every_document_the_writeup_names_as_failing_did_fail() -> None:
    text = WRITEUP.read_text(encoding="utf-8")
    for record in _records():
        name = record["url"].rsplit("/", 1)[-1]
        if record.get("summary", {}).get("ERROR"):
            assert name in text, f"{name} carried ERRORs and is not named in the write-up"


def test_the_writeup_never_claims_conformance_from_a_clean_run() -> None:
    text = WRITEUP.read_text(encoding="utf-8")
    assert "has not been shown to conform" in text
    assert "No percentage here is a population estimate" in text.replace("\n", " ")
