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
WIDENED_TARGETS = ROOT / "tools" / "survey-urls-2026-08-19.txt"
FINDINGS = ROOT / "docs" / "findings"

WITHHELD = FINDINGS / "2026-08-14-published-oscal-survey.json"
WITHHELD_WRITEUP = FINDINGS / "2026-08-14-published-oscal-survey.md"
SUPPLIED = FINDINGS / "2026-08-15-imports-supplied-survey.json"
SUPPLIED_WRITEUP = FINDINGS / "2026-08-15-imports-supplied-survey.md"
WIDENED = FINDINGS / "2026-08-19-widening-the-corpus-survey.json"
WIDENED_WRITEUP = FINDINGS / "2026-08-19-widening-the-corpus-survey.md"
CONSTRAINTS_REACHED = FINDINGS / "2026-08-19-constraints-reached-survey.json"
CONSTRAINTS_REACHED_WRITEUP = FINDINGS / "2026-08-19-constraints-reached-survey.md"
IMPORTS_REACHED = FINDINGS / "2026-08-19-imports-reached-survey.json"
IMPORTS_REACHED_WRITEUP = FINDINGS / "2026-08-19-imports-reached-survey.md"

PAIRS = [
    (WITHHELD, WITHHELD_WRITEUP),
    (SUPPLIED, SUPPLIED_WRITEUP),
    (WIDENED, WIDENED_WRITEUP),
    (CONSTRAINTS_REACHED, CONSTRAINTS_REACHED_WRITEUP),
    (IMPORTS_REACHED, IMPORTS_REACHED_WRITEUP),
]

#: Which target list each run was drawn from. The 2026-08-14 and 2026-08-15 runs
#: share one; the 2026-08-19 run widens the corpus and has its own, so that a
#: dated artifact keeps naming the exact inputs it ran on rather than whatever
#: the list has grown into since.
IMPORTS_TARGETS = ROOT / "tools" / "survey-urls-2026-08-19-imports.txt"
DRAWN_FROM = {
    WITHHELD: TARGETS,
    SUPPLIED: TARGETS,
    WIDENED: WIDENED_TARGETS,
    CONSTRAINTS_REACHED: WIDENED_TARGETS,
    IMPORTS_REACHED: IMPORTS_TARGETS,
}

TARGET_LISTS = [TARGETS, WIDENED_TARGETS, IMPORTS_TARGETS]

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


def _severities(survey: Path) -> Counter[str]:
    """Severity -> count, summed over every record's own severity summary."""
    totals: Counter[str] = Counter()
    for record in _records(survey):
        totals.update(record.get("summary", {}))
    return Counter({severity: count for severity, count in totals.items() if count})


#: A row of the write-up's finding-totals table: code, severity, count.
_SEVERITY_ROW = re.compile(
    r"^\|\s*`([A-Z_]+)`\s*\|\s*(ERROR|WARNING|UNVERIFIABLE|INFO)\s*\|\s*([\d,]+)\s*\|$"
)


def _severity_rows(writeup: Path) -> list[tuple[str, str, int]]:
    rows = []
    for line in writeup.read_text(encoding="utf-8").splitlines():
        match = _SEVERITY_ROW.match(line.strip())
        if match:
            rows.append((match[1], match[2], int(match[3].replace(",", ""))))
    return rows


def _headline(writeup: Path) -> dict[str, int]:
    """Label -> count, from the write-up's first table."""
    found: dict[str, int] = {}
    for line in writeup.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) >= 4 and re.fullmatch(r"\d+", cells[2]):
            found.setdefault(cells[1], int(cells[2]))
    return found


def _target_lines(targets: Path = TARGETS) -> list[list[str]]:
    return [
        line.split("\t")
        for line in targets.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _targets(targets: Path = TARGETS) -> list[str]:
    return [parts[1] for parts in _target_lines(targets)]


@pytest.mark.parametrize("targets", TARGET_LISTS)
def test_the_target_list_is_well_formed(targets: Path) -> None:
    for line in targets.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        assert len(parts) in (2, 3), f"expected group<TAB>url[<TAB>resolve]: {line!r}"
        assert parts[0].strip() and not parts[0].startswith(" ")
        assert parts[1].startswith("https://"), parts[1]
        for resolve in parts[2].split(",") if len(parts) > 2 else []:
            assert resolve.startswith("https://"), resolve
            assert resolve != parts[1], f"a document cannot resolve against itself: {resolve}"
    urls = _targets(targets)
    assert len(set(urls)) == len(urls), "a duplicate URL would double-count a document"


def test_no_document_is_surveyed_by_two_runs() -> None:
    """The corpus grows by addition. A target counted twice is counted twice.

    The write-ups add their denominators together to state a corpus size, which
    is only honest while the target lists are disjoint.
    """
    first, second = set(_targets(TARGETS)), set(_targets(WIDENED_TARGETS))
    assert not first & second, sorted(first & second)


@pytest.mark.parametrize(
    "survey", [WITHHELD, SUPPLIED, WIDENED, CONSTRAINTS_REACHED, IMPORTS_REACHED]
)
def test_every_target_appears_in_the_survey_exactly_once(survey: Path) -> None:
    assert [record["url"] for record in _records(survey)] == _targets(DRAWN_FROM[survey])


@pytest.mark.parametrize("survey", [WITHHELD, SUPPLIED, WIDENED])
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
    """Every code, and the severity it was actually recorded at.

    A code is not tied to one severity: a constraint finding carries the level
    NIST declares on the constraint, so ``CONSTRAINT_CARDINALITY`` is emitted at
    both ERROR and WARNING. Asserting a code's total against a severity typed
    into the table is therefore not enough, and an earlier version of this test
    did exactly that: it took the count from the evidence and the word ERROR
    from nowhere, which let the write-ups publish ten warnings as errors. The
    severity columns are now summed and checked against the per-severity totals
    the run recorded, so the table cannot claim a severity the run did not.
    """
    rows = _severity_rows(writeup)
    assert rows, "no finding-totals table found in the write-up"

    by_code: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    for code, severity, count in rows:
        by_code[code] += count
        by_severity[severity] += count

    assert by_code == _totals(survey), "the table's per-code totals are not the evidence's"
    assert by_severity == _severities(survey), "the table's severities are not the ones recorded"


@pytest.mark.parametrize(("survey", "writeup"), PAIRS)
def test_every_document_the_writeup_names_as_failing_did_fail(survey: Path, writeup: Path) -> None:
    text = writeup.read_text(encoding="utf-8")
    for record in _records(survey):
        name = record["url"].rsplit("/", 1)[-1]
        if record.get("summary", {}).get("ERROR"):
            assert name in text, f"{name} carried ERRORs and is not named in the write-up"


@pytest.mark.parametrize(
    "writeup",
    [
        WITHHELD_WRITEUP,
        SUPPLIED_WRITEUP,
        WIDENED_WRITEUP,
        CONSTRAINTS_REACHED_WRITEUP,
        IMPORTS_REACHED_WRITEUP,
    ],
)
def test_the_writeup_never_claims_conformance_from_a_clean_run(writeup: Path) -> None:
    text = writeup.read_text(encoding="utf-8")
    assert "has not been shown to conform" in text
    assert "No percentage here is a population estimate" in text.replace("\n", " ")


# -- the second run, whose subject is the difference ------------------------


@pytest.mark.parametrize("survey", [SUPPLIED, WIDENED, CONSTRAINTS_REACHED, IMPORTS_REACHED])
def test_a_run_supplied_exactly_what_its_resolve_column_declared(survey: Path) -> None:
    lines = _target_lines(DRAWN_FROM[survey])
    declared = {parts[1]: parts[2].split(",") if len(parts) > 2 else [] for parts in lines}
    for record in _records(survey):
        assert record["resolve"] == declared[record["url"]], record["url"]


def test_the_withheld_run_supplied_only_what_its_own_column_declared() -> None:
    """The 2026-08-14 evidence predates the resolve column being filled in.

    Its records carry no ``resolve`` key at all, and the delta below is only
    meaningful if that run really did withhold what this one supplies.
    """
    supplied_edges = sum(r.get("imports_resolved", 0) for r in _records(SUPPLIED))
    withheld_edges = sum(r.get("imports_resolved", 0) for r in _records(WITHHELD))
    assert withheld_edges < supplied_edges


@pytest.mark.parametrize("survey", [SUPPLIED, WIDENED, CONSTRAINTS_REACHED, IMPORTS_REACHED])
def test_every_supporting_document_is_named_by_some_target(survey: Path) -> None:
    lines = _target_lines(DRAWN_FROM[survey])
    named = {url for parts in lines if len(parts) > 2 for url in parts[2].split(",")}
    listed = {entry["url"] for entry in _payload(survey)["supporting"]}
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


# -- the third run, whose subject is the corpus itself -----------------------


def _model_roots() -> set[str]:
    """OSCAL's model root elements, read off the vendored schema rather than typed.

    The eighth is the point of the third run, and a list of eight names in a
    test is exactly the kind of thing that silently becomes a list of seven.
    """
    schema = json.loads(
        (ROOT / "src" / "oscal_validate" / "vendor" / "oscal" / "complete_schema.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        name
        for alternative in schema["oneOf"]
        for name in alternative["properties"]
        if name != "$schema"
    }


def test_the_corpus_covers_every_model_the_vendored_schema_accepts() -> None:
    surveyed = {record["model"] for survey in (SUPPLIED, WIDENED) for record in _records(survey)}
    missing = _model_roots() - surveyed
    assert not missing, f"no real published document in the corpus uses {sorted(missing)}"


def test_the_eighth_model_arrived_with_the_widened_run() -> None:
    """The claim the 2026-08-19 write-up is built on, kept true by measurement."""
    before = {record["model"] for record in _records(SUPPLIED)}
    after = {record["model"] for record in _records(WIDENED)}
    assert _model_roots() - before == {"mapping-collection"}
    assert "mapping-collection" in after


def test_the_model_table_is_the_sum_of_both_samples() -> None:
    """Every row of the widened write-up's model table, recomputed from the JSONs."""
    before: Counter[str] = Counter()
    after: Counter[str] = Counter()
    for record in _records(SUPPLIED):
        before[record["model"]] += 1
    for record in _records(WIDENED):
        after[record["model"]] += 1
    text = WIDENED_WRITEUP.read_text(encoding="utf-8")
    for model in sorted(_model_roots()):
        highlight = "**" if model == "mapping-collection" else ""
        row = (
            f"| `{model}` | {highlight}{before[model]}{highlight} | "
            f"{highlight}{after[model]}{highlight} | "
            f"{highlight}{before[model] + after[model]}{highlight} |"
        )
        assert row in text, f"model row missing or wrong for {model}: expected {row!r}"


def test_the_unread_mapping_subtree_is_reported_on_every_mapping_collection() -> None:
    """Finding 1: the eighth model's content is not read, and says so every time.

    If a future change makes the walker resolve that subtree, this test fails and
    the write-up has to be corrected rather than left claiming a limit that is no
    longer there. A stale limitation is as misleading as a stale number.
    """
    mappings = [r for r in _records(WIDENED) if r["model"] == "mapping-collection"]
    assert mappings, "the widened run exists to put this model in the corpus"
    for record in mappings:
        assert record["codes"].get("SUBTREE_NOT_READ"), record["url"]
        assert record["example_location"]["SUBTREE_NOT_READ"] == "/mapping-collection/mappings"


# -- the fourth and fifth runs: the engine, then the imports ------------------


def _delta_rows_present(before_path: Path, after_path: Path, writeup: Path) -> None:
    before, after = _totals(before_path), _totals(after_path)
    text = writeup.read_text(encoding="utf-8")
    codes = sorted(set(before) | set(after))
    assert codes, "no finding codes in either run"
    for code in codes:
        change = after[code] - before[code]
        row = (
            f"| `{code}` | {before[code]:,} | {after[code]:,} | "
            f"{'+' if change > 0 else ''}{change:,} |"
        )
        assert row in text, f"delta row missing or wrong for {code}: expected {row!r}"


def _settled_split_present(before_path: Path, after_path: Path, writeup: Path) -> None:
    before, after = _totals(before_path), _totals(after_path)
    unsettled_before = before["REFERENCE_UNVERIFIABLE"]
    still_unsettled = after["REFERENCE_UNVERIFIABLE"]
    became_errors = after["REFERENCE_UNRESOLVED"] - before["REFERENCE_UNRESOLVED"]
    resolved_clean = unsettled_before - still_unsettled - became_errors
    assert became_errors >= 0 and resolved_clean >= 0
    text = writeup.read_text(encoding="utf-8")
    for label, value in (
        ("resolved to something that exists", resolved_clean),
        ("resolved to nothing, and are now ERROR", became_errors),
        ("still cannot be settled", still_unsettled),
    ):
        assert f"| {label} | {value:,} |" in text, f"{label} should be {value:,}"


def test_the_engine_delta_table_is_the_difference_between_the_two_runs() -> None:
    """The constraints run's subject is the engine; its tables are recomputed here."""
    _delta_rows_present(WIDENED, CONSTRAINTS_REACHED, CONSTRAINTS_REACHED_WRITEUP)
    _settled_split_present(WIDENED, CONSTRAINTS_REACHED, CONSTRAINTS_REACHED_WRITEUP)


def test_the_engine_run_found_no_new_violations_and_says_so() -> None:
    """The constraints run's headline claim, kept true by measurement.

    Zero new ERRORs from 24 newly reached constraints is a strong sentence, and
    it must fall out of the evidence rather than out of enthusiasm: the ERROR
    totals of the two runs must be equal, and the write-up must say zero.
    """
    before, after = _severities(WIDENED), _severities(CONSTRAINTS_REACHED)
    assert before["ERROR"] == after["ERROR"]
    text = CONSTRAINTS_REACHED_WRITEUP.read_text(encoding="utf-8").replace("\n", " ")
    assert "zero new violations" in text


def test_the_imports_delta_table_is_the_difference_between_the_two_runs() -> None:
    """The imports run's subject is the resolve column; its tables are recomputed here."""
    _delta_rows_present(CONSTRAINTS_REACHED, IMPORTS_REACHED, IMPORTS_REACHED_WRITEUP)
    _settled_split_present(CONSTRAINTS_REACHED, IMPORTS_REACHED, IMPORTS_REACHED_WRITEUP)


def test_the_imports_run_documents_that_stayed_unsettled_are_all_named() -> None:
    text = IMPORTS_REACHED_WRITEUP.read_text(encoding="utf-8")
    incomplete = [
        r for r in _records(IMPORTS_REACHED) if not r.get("effective_model_complete", True)
    ]
    assert incomplete, "the whole point is that some documents could not be completed"
    for record in incomplete:
        name = record["url"].rsplit("/", 1)[-1]
        assert name in text, f"{name} stayed incomplete and is not named in the write-up"


def test_the_paired_runs_share_their_corpus_and_differ_only_where_stated() -> None:
    """The engine pair shares bytes; the imports pair shares bytes and engine.

    Both comparisons above are only attributable because everything else is
    pinned: the three runs survey the same 43 URLs, and the per-record byte
    counts are identical across all three.
    """
    by_url = {}
    for survey in (WIDENED, CONSTRAINTS_REACHED, IMPORTS_REACHED):
        by_url[survey] = {r["url"]: r["bytes"] for r in _records(survey)}
    assert by_url[WIDENED].keys() == by_url[CONSTRAINTS_REACHED].keys()
    assert by_url[WIDENED].keys() == by_url[IMPORTS_REACHED].keys()
    assert by_url[WIDENED] == by_url[CONSTRAINTS_REACHED]
    assert by_url[WIDENED] == by_url[IMPORTS_REACHED]
