"""``--locations``: where a finding's pointer points in the source bytes.

Three things have to hold at once and each is easy to lose separately.

**The index has to be right.** ``test_the_index_reaches_every_pointer_the_document_has``
walks the decoded document itself and compares pointer sets, so the scanner is
measured against ``json.loads`` rather than against its own output.

**The default path may not move.** ``tests/golden/`` holds the bytes of a run
without the flag, and the tests here add the direct version of that claim:
without ``--locations`` the JSON report carries no ``line`` key at all, and the
text report's first line is what it always was.

**An absent position may not be published as a number.** Under the flag, a
finding this run has no position for prints ``null`` in JSON and words in text.
Line 0 does not exist, and a fabricated 1 would put a finding on the first line
of a file and be indistinguishable from a measured one.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from oscal_validate import Position, validate_file
from oscal_validate.baseline import BASELINE_VERSION, Baseline, Entry, apply
from oscal_validate.findings import NO_POSITION, render_findings_json, render_findings_text
from oscal_validate.positions import PositionError, SourceIndex, index_document

from .conftest import fixture_path, load_fixture, write

ROOT = Path(__file__).resolve().parent.parent
MATCHER = ROOT / ".github" / "problem-matcher.json"

#: The document every "done when" bullet of issue #66 is written about.
BROKEN = "broken_catalog.json"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "oscal_validate", *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )


def _pointers(value: Any, pointer: str = "") -> set[str]:
    """Every JSON Pointer in a decoded document, from the decoded document.

    Deliberately not the scanner's own walk: this is the independent side of
    the comparison, and if it shared code with the thing it measures it would
    only prove the two agree with themselves.
    """
    found = {pointer}
    if isinstance(value, dict):
        for key, child in value.items():
            token = str(key).replace("~", "~0").replace("/", "~1")
            found |= _pointers(child, f"{pointer}/{token}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found |= _pointers(child, f"{pointer}/{index}")
    return found


# -- the index ---------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["broken_catalog.json", "clean_catalog.json", "clean_profile.json", "nist_ssp_example.json"],
)
def test_the_index_reaches_every_pointer_the_document_has(name: str) -> None:
    """Not "most of them". The two sets are equal, in both directions.

    A scanner that silently stopped early would still answer correctly for
    every pointer it did reach, and a report built on it would look complete.
    """
    path = fixture_path(name)
    index = index_document(str(path), path.read_text(encoding="utf-8"))
    expected = _pointers(load_fixture(name))
    reached = {pointer for pointer in expected if index.position(pointer) is not None}
    assert reached == expected, f"{len(expected) - len(reached)} pointer(s) missing from the index"
    assert len(index) == len(expected)


def test_every_recorded_position_is_the_first_character_of_that_value() -> None:
    """The offset must be the value, not the key and not the comma before it."""
    path = fixture_path(BROKEN)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    index = index_document(str(path), text)
    for pointer, expected in (
        ("", "{"),
        ("/catalog", "{"),
        ("/catalog/metadata", "{"),
        ("/catalog/metadata/title", '"'),
        ("/catalog/groups", "["),
        ("/catalog/groups/0", "{"),
    ):
        position = index.position(pointer)
        assert position is not None, pointer
        assert lines[position.line - 1][position.column - 1] == expected, pointer


def test_a_duplicate_key_records_the_position_json_loads_keeps(tmp_path: Path) -> None:
    """``json.loads`` keeps the last of two same-named members. So does this.

    Recording the first would point a reader at a value the rest of the report
    is not about.
    """
    source = '{"a": 1,\n "a": 2}\n'
    path = tmp_path / "duplicate.json"
    path.write_text(source, encoding="utf-8")
    assert json.loads(source)["a"] == 2
    position = index_document(str(path), source).position("/a")
    assert position is not None
    assert position.line == 2


def test_a_pointer_token_is_escaped_the_way_the_document_walk_escapes_it(
    tmp_path: Path,
) -> None:
    """RFC 6901: ``~`` is ``~0`` and ``/`` is ``~1``. Both, in one key."""
    source = '{"a/b~c": 1}'
    path = tmp_path / "escaped.json"
    path.write_text(source, encoding="utf-8")
    index = index_document(str(path), source)
    assert index.position("/a~1b~0c") is not None
    assert index.position("/a/b~c") is None


def test_an_empty_container_has_a_position_and_no_children(tmp_path: Path) -> None:
    source = '{"empty_object": {}, "empty_array": [], "after": 1}'
    path = tmp_path / "empty.json"
    path.write_text(source, encoding="utf-8")
    index = index_document(str(path), source)
    assert index.position("/empty_object") is not None
    assert index.position("/empty_array") is not None
    assert index.position("/after") is not None
    assert len(index) == 4


def test_the_scanner_refuses_text_it_cannot_read_rather_than_indexing_half_of_it(
    tmp_path: Path,
) -> None:
    """A hole in the index is indistinguishable from a pointer with no position.

    The reader only ever sees text ``json.loads`` already accepted, so this
    cannot happen in a run; it is here so that if it ever does, it is loud.
    """
    path = tmp_path / "broken.json"
    for source in ('{"a": 1', '{"a" 1}', '{"a": 1} trailing', "{,}"):
        with pytest.raises(PositionError):
            index_document(str(path), source)


def test_a_position_is_one_based_in_both_axes(tmp_path: Path) -> None:
    """There is no line 0 and no column 0, which is why a missing one is None."""
    source = '{"a": 1}'
    path = tmp_path / "one.json"
    path.write_text(source, encoding="utf-8")
    index = index_document(str(path), source)
    assert index.position("") == Position(file=str(path), line=1, column=1)
    assert index.position("/a") == Position(file=str(path), line=1, column=7)


# -- what the findings carry -------------------------------------------------


def test_every_finding_in_the_broken_catalog_is_located_in_the_broken_catalog() -> None:
    """Issue #66's first "done when", with its denominator printed.

    ``examined / examinable`` rather than a pass: a check that quietly located
    two findings of eight would read exactly like this one.
    """
    findings = validate_file(fixture_path(BROKEN), locations=True)
    assert findings, "the fixture must produce findings or this test measures nothing"
    located = [f for f in findings if f.position is not None]
    assert len(located) == len(findings), (
        f"{len(located)} of {len(findings)} findings carry a position"
    )
    assert {f.position.file for f in located if f.position} == {str(fixture_path(BROKEN))}


def test_the_recorded_line_holds_the_value_a_scalar_finding_quotes() -> None:
    """The value as written must be on the line the finding names.

    Issue #66 asks for this of ``broken_catalog.json``, and **that document
    cannot answer it**: measured here, all eight of its findings point at the
    document root, at an object, or at an array element -- none at a scalar,
    so none has a `value` that is text in the file. The bullet is right about
    what has to be true and wrong about where to look, so the sweep is over
    every committed fixture and the population it found is asserted rather
    than assumed.
    """
    scalar_findings = 0
    total = 0
    for name in (
        BROKEN,
        "clean_catalog.json",
        "clean_profile.json",
        "clean_mapping_collection.json",
        "nist_ssp_example.json",
    ):
        path = fixture_path(name)
        lines = path.read_text(encoding="utf-8").splitlines()
        document = load_fixture(name)
        for finding in validate_file(path, locations=True):
            total += 1
            target: Any = document
            for token in finding.location.split("/")[1:]:
                key = token.replace("~1", "/").replace("~0", "~")
                target = target[int(key)] if isinstance(target, list) else target[key]
            if isinstance(target, dict | list):
                continue
            scalar_findings += 1
            assert finding.position is not None, f"{name}: {finding.code}"
            assert finding.value in lines[finding.position.line - 1], f"{name}: {finding.code}"
    assert scalar_findings >= 8, (
        f"{scalar_findings} of {total} findings point at a scalar; the assertion above is "
        "about that population and cannot be satisfied by an empty one"
    )


def test_reformatting_the_document_moves_the_lines_and_nothing_else(tmp_path: Path) -> None:
    """Issue #66's second "done when", in both directions.

    The pointer is the key and it does not move when a file is reformatted;
    the position does, which is the whole reason a position cannot replace a
    pointer.
    """
    document = load_fixture(BROKEN)
    two = tmp_path / "indent2.json"
    four = tmp_path / "indent4.json"
    two.write_text(json.dumps(document, indent=2), encoding="utf-8")
    four.write_text(json.dumps(document, indent=4), encoding="utf-8")

    narrow = validate_file(two, locations=True)
    wide = validate_file(four, locations=True)

    assert [f.location for f in narrow] == [f.location for f in wide]
    assert render_findings_json(narrow, "0", "catalog") == render_findings_json(
        wide, "0", "catalog"
    )
    moved = [
        (a.position, b.position)
        for a, b in zip(narrow, wide, strict=True)
        if a.position != b.position
    ]
    assert moved, "reformatting moved no line, so this test proves nothing about positions"


def test_a_pointer_the_source_does_not_carry_reports_nothing_at_all() -> None:
    """An index that has never seen a pointer says None, and None is not 0."""
    path = fixture_path(BROKEN)
    index = index_document(str(path), path.read_text(encoding="utf-8"))
    assert index.position("/catalog/there-is-no-such-property") is None


def test_a_finding_in_a_resolved_document_is_located_in_that_document() -> None:
    """``<path>#<pointer>`` locates in the supplied file, not in the primary one."""
    catalog = fixture_path("clean_catalog.json")
    findings = validate_file(fixture_path("clean_profile.json"), [catalog], locations=True)
    qualified = [f for f in findings if f.location.startswith(f"{catalog}#")]
    for finding in qualified:
        assert finding.position is not None
        assert finding.position.file == str(catalog)
    assert all(
        f.position is None or f.position.file == str(fixture_path("clean_profile.json"))
        for f in findings
        if not f.location.startswith(f"{catalog}#")
    )


# -- the renderings ----------------------------------------------------------


def test_without_the_flag_the_report_makes_no_claim_about_position() -> None:
    """Absent, not null. A run that was not asked answers nothing."""
    findings = validate_file(fixture_path(BROKEN))
    payload = json.loads(render_findings_json(findings, "0", "catalog"))
    for finding in payload["findings"]:
        assert "line" not in finding
        assert "column" not in finding
    assert NO_POSITION not in render_findings_text(findings, "catalog")


def test_with_the_flag_every_finding_carries_both_keys() -> None:
    findings = validate_file(fixture_path(BROKEN), locations=True)
    payload = json.loads(render_findings_json(findings, "0", "catalog", locations=True))
    for finding in payload["findings"]:
        assert isinstance(finding["line"], int)
        assert isinstance(finding["column"], int)
        assert finding["line"] >= 1
        assert finding["column"] >= 1


def test_a_finding_with_no_position_renders_null_and_words_never_zero() -> None:
    """The three-valued contract, at the one value that is easy to fake."""
    findings = validate_file(fixture_path(BROKEN), locations=True)
    unlocated = [f.__class__(**{**f.__dict__, "position": None}) for f in findings[:1]]
    payload = json.loads(render_findings_json(unlocated, "0", "catalog", locations=True))
    assert payload["findings"][0]["line"] is None
    assert payload["findings"][0]["column"] is None
    assert NO_POSITION in render_findings_text(unlocated, "catalog", locations=True)
    assert ":0:" not in render_findings_text(unlocated, "catalog", locations=True)


def test_the_text_report_puts_the_position_on_the_line_the_matcher_reads() -> None:
    completed = _run(str(fixture_path(BROKEN)), "--locations")
    assert completed.returncode == 1, completed.stderr
    heads = [line for line in completed.stdout.splitlines() if line.startswith("ERROR ")]
    assert heads
    for head in heads:
        assert re.search(r"\s\S+:\d+:\d+$", head), head


def test_sarif_and_html_are_untouched_by_the_flag() -> None:
    """A flag that appears to reach a format it does not reach is worse than
    one that says so. ``--locations``' help text says these two are unchanged;
    this is what holds it to that, and what will go red the day one of them
    learns to carry a position."""
    for fmt in ("sarif", "html"):
        without = _run(str(fixture_path(BROKEN)), "--format", fmt)
        with_flag = _run(str(fixture_path(BROKEN)), "--format", fmt, "--locations")
        assert without.stdout == with_flag.stdout, fmt
        assert without.returncode == with_flag.returncode, fmt


def test_the_flag_is_deterministic_across_processes() -> None:
    runs = [_run(str(fixture_path(BROKEN)), "--locations", "--format", "json") for _ in range(2)]
    assert runs[0].stdout == runs[1].stdout
    assert runs[0].stdout


# -- --baseline, which builds findings after validate has returned -----------


def _baseline_for(tmp_path: Path, finding_code: str) -> Path:
    findings = validate_file(fixture_path(BROKEN), locations=True)
    match = next(f for f in findings if f.code == finding_code)
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps(
            {
                "baseline_version": BASELINE_VERSION,
                "entries": [
                    {
                        "code": match.code,
                        "location": match.location,
                        "property": match.prop,
                        "value": match.value,
                        "reason": "recorded so this test has something to acknowledge",
                        "acknowledged_on": "2026-09-09",
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def test_baseline_apply_carries_the_position_onto_the_acknowledged_copy() -> None:
    """``baseline._acknowledged_copy`` names every field it copies, one by one.

    A field left off that list is not inherited from anywhere; the copy loses
    it silently. This is asserted against ``baseline.apply`` directly rather
    than through the CLI, and the reason is a control that did not fire: the
    CLI re-attaches positions after a baseline is applied (it has to, for
    ``BASELINE_STALE``), so deleting the field from the copy leaves every
    end-to-end assertion green while the library function quietly drops it for
    any caller that does not re-attach.
    """
    findings = validate_file(fixture_path(BROKEN), locations=True)
    match = next(f for f in findings if f.code == "REQUIRED_PROPERTY_MISSING")
    assert match.position is not None
    entry = Entry(
        finding_code=match.code,
        location=match.location,
        prop=match.prop,
        value=match.value,
        reason="recorded so this test has something to acknowledge",
        acknowledged_on="2026-09-09",
    )
    applied = apply(findings, Baseline(path=Path("baseline.json"), entries=(entry,)))
    acknowledged = [f for f in applied if f.acknowledged is not None]
    assert len(acknowledged) == 1
    assert acknowledged[0].position == match.position


def test_an_acknowledged_finding_keeps_the_position_it_had(tmp_path: Path) -> None:
    """The same claim end to end, through the CLI."""
    path = _baseline_for(tmp_path, "REQUIRED_PROPERTY_MISSING")
    completed = _run(
        str(fixture_path(BROKEN)), "--locations", "--baseline", str(path), "--format", "json"
    )
    payload = json.loads(completed.stdout)
    acknowledged = [f for f in payload["findings"] if "acknowledged" in f]
    assert len(acknowledged) == 1
    assert isinstance(acknowledged[0]["line"], int)


def test_a_stale_baseline_entry_is_located_like_every_other_finding(tmp_path: Path) -> None:
    """A BASELINE_STALE finding is made after ``validate`` returned.

    It still names a pointer, and that pointer is usually still in the file --
    which is exactly what a reader needs to go and look. Without the second
    ``attach`` in the CLI it would be the only positionless row in the report.
    """
    entry = {
        "code": "UUID_NOT_UNIQUE",
        "location": "/catalog/metadata",
        "property": "uuid",
        "value": "nothing in this run reports this",
        "reason": "kept so the entry goes stale",
        "acknowledged_on": "2026-09-09",
    }
    path = tmp_path / "stale.json"
    path.write_text(
        json.dumps({"baseline_version": BASELINE_VERSION, "entries": [entry]}), encoding="utf-8"
    )
    completed = _run(
        str(fixture_path(BROKEN)), "--locations", "--baseline", str(path), "--format", "json"
    )
    payload = json.loads(completed.stdout)
    stale = [f for f in payload["findings"] if f["code"] == "BASELINE_STALE"]
    assert len(stale) == 1
    assert isinstance(stale[0]["line"], int), "the stale entry names a pointer that is in the file"


# -- the problem matcher -----------------------------------------------------


def _matchers() -> list[dict[str, Any]]:
    payload: dict[str, Any] = json.loads(MATCHER.read_text(encoding="utf-8"))
    matchers: list[dict[str, Any]] = payload["problemMatcher"]
    return matchers


def test_the_problem_matcher_reads_the_tools_own_output() -> None:
    """Regexes tested against real bytes, not against an example in a docstring.

    What this proves: the patterns match the text this tool prints and capture
    the file, line, column and code correctly. What it does not prove: that
    GitHub applies them. That is stated in the README beside the snippet
    rather than implied by a green test here.
    """
    completed = _run(str(fixture_path(BROKEN)), "--locations")
    lines = completed.stdout.splitlines()
    document = str(fixture_path(BROKEN))

    matched: list[tuple[str, str, int, int]] = []
    for matcher in _matchers():
        head = re.compile(matcher["pattern"][0]["regexp"])
        for offset, line in enumerate(lines):
            found = head.match(line)
            if found is None:
                continue
            assert re.match(matcher["pattern"][1]["regexp"], lines[offset + 1]), line
            message = re.match(matcher["pattern"][2]["regexp"], lines[offset + 2])
            assert message is not None and message.group(1), line
            matched.append(
                (found.group(1), found.group(3), int(found.group(4)), int(found.group(5)))
            )

    findings = validate_file(fixture_path(BROKEN), locations=True)
    assert len(matched) == len(findings), (
        f"the matcher read {len(matched)} of {len(findings)} findings out of the text report"
    )
    assert {file for _, file, _, _ in matched} == {document}
    assert {(code, line, column) for code, _, line, column in matched} == {
        (f.code, f.position.line, f.position.column) for f in findings if f.position
    }


def test_the_matcher_severities_are_the_mapping_the_action_already_uses() -> None:
    """One four-into-three mapping, in two files, held together.

    ``tools/action_runner.py`` maps the tool's four severities onto GitHub's
    three annotation levels and has been doing so in CI since the Action
    shipped. The matcher must not invent a second answer.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    from action_runner import LEVELS, SEVERITIES  # noqa: PLC0415

    declared: dict[str, str] = {}
    for matcher in _matchers():
        head = matcher["pattern"][0]["regexp"]
        for severity in SEVERITIES:
            if re.match(head, f"{severity:12} CODE  at=/x  f.json:1:1"):
                declared[severity] = matcher["severity"]
    assert declared == LEVELS
    assert len({matcher["owner"] for matcher in _matchers()}) == len(_matchers())


def test_a_finding_with_no_position_is_not_matched_at_all() -> None:
    """A matcher cannot annotate without a file, and the text report does not
    print one where there is no position. Silence is the right answer; a
    fabricated file and line would not be."""
    head = re.compile(_matchers()[0]["pattern"][0]["regexp"])
    assert head.match(f"ERROR        CODE  at=/catalog  {NO_POSITION}") is None


# -- the Action --------------------------------------------------------------


def _annotations(document: Path) -> list[str]:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "action_runner.py")],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src"), "OSCAL_PATH": str(document)},
    )
    return [line for line in completed.stdout.splitlines() if line.startswith("::")]


def test_the_action_annotates_the_broken_fixture_on_the_line_the_report_names() -> None:
    """Issue #66's third "done when", run here as well as on the runner."""
    findings = validate_file(fixture_path(BROKEN), locations=True)
    expected = {
        f"line={f.position.line},col={f.position.column}"
        for f in findings
        if f.position is not None
    }
    assert expected, "the fixture must produce a located finding"
    annotations = _annotations(fixture_path(BROKEN))
    assert annotations
    for pair in expected:
        assert any(pair in annotation for annotation in annotations), pair


@pytest.mark.parametrize(
    ("line", "column", "expected"),
    [
        (None, None, ""),
        (0, 5, ""),
        (12, 0, "line=12"),
        (12, 5, "line=12,col=5"),
        (True, 5, ""),
        ("12", 5, ""),
    ],
)
def test_the_action_refuses_a_position_that_is_not_a_position(
    line: object, column: object, expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """0 is not a line and ``True`` is not a line, and GitHub would anchor on
    either. A column without a line means nothing to GitHub, so it is dropped
    rather than emitted alone."""
    sys.path.insert(0, str(ROOT / "tools"))
    from action_runner import annotate, position_of  # noqa: PLC0415

    resolved_line, resolved_column = position_of({"line": line, "column": column})
    annotate("error", "m", file="f.json", line=resolved_line, column=resolved_column)
    printed = capsys.readouterr().out
    if expected:
        assert expected in printed
    else:
        assert "line=" not in printed


def test_the_action_asks_for_positions(tmp_path: Path) -> None:
    """The one line that makes every annotation above possible.

    Removing ``locations=True`` from the Action's own CLI call leaves every
    other assertion in this file green, because they read the CLI directly.
    """
    source = (ROOT / "tools" / "action_runner.py").read_text(encoding="utf-8")
    assert "locations=True" in source
    document = write(tmp_path, "clean_catalog.json", load_fixture("clean_catalog.json"))
    assert any("line=" in annotation for annotation in _annotations(document))


# -- the source index is only built when it is asked for ---------------------


def test_no_index_is_built_without_the_flag() -> None:
    from oscal_validate import build_session  # noqa: PLC0415

    off = build_session(fixture_path(BROKEN))
    assert all(document.source is None for document in off.corpus.reachable)
    on = build_session(fixture_path(BROKEN), locations=True)
    assert all(isinstance(document.source, SourceIndex) for document in on.corpus.reachable)
