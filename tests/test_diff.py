"""``oscal-validate diff``: the comparison, the provenance it cannot see, and the words.

The comparison itself is small. What these tests hold is the honesty around it:
that a finding which disappeared is called removed and not resolved, that a
saved report's silence about which vendored snapshot produced it is printed as
unknown rather than passed over, that a move is only claimed where it can be
decided, and that the verb reaches no model and no socket.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from oscal_validate import compare as compare_module
from oscal_validate.cli import DETERMINISTIC_COMMANDS, main
from oscal_validate.compare import ReportError, compare, findings_from_report
from oscal_validate.diff import Side, provenance_notes, render_text
from oscal_validate.findings import Finding, Rule, Severity
from oscal_validate.positions import Position
from oscal_validate.validator import validate_file

from .conftest import FIXTURES, fixture_path, load_fixture, write

CLEAN = fixture_path("clean_catalog.json")
BROKEN = fixture_path("broken_catalog.json")


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = main(["diff", *argv])
    return code, capsys.readouterr().out


def _report(tmp_path: Path, name: str, document: Path, version: str = "9.9.9") -> Path:
    """A saved ``--format json`` report, as the default command writes them."""
    findings = validate_file(document, None)
    payload = {
        "tool": {"name": "oscal-validate", "version": version},
        "document": {"model": "catalog"},
        "findings": [f.to_dict() for f in findings],
        "summary": {},
    }
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _side(*findings: Finding) -> Side:
    """A `Side` built here rather than loaded, so `render_text` can be reached
    without a file for every shape the comparison can produce."""
    return Side(
        path=Path("side.json"),
        findings=list(findings),
        origin="document",
        tool_version="9.9.9",
        snapshot="1.2.3",
    )


def _finding(location: str, value: str = "x", code: str = "REFERENCE_UNRESOLVED") -> Finding:
    return Finding(
        code=code,
        severity=Severity.ERROR,
        location=location,
        prop="href",
        value=value,
        message="m",
        rule=Rule(citation="c", url="u", retrieved="-"),
    )


# -- the comparison ----------------------------------------------------------


def test_identical_inputs_produce_an_empty_diff(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, str(CLEAN), str(CLEAN))
    assert code == 0
    assert out.count("(none)") == 4
    assert "0 unchanged" not in out


def test_the_three_seeded_errors_are_listed_as_added(capsys: pytest.CaptureFixture[str]) -> None:
    """The fixture pair the whole tool's break-the-gate evidence rests on."""
    code, out = _run(capsys, str(CLEAN), str(BROKEN), "--format", "json")
    assert code == 0
    payload = json.loads(out)
    added = payload["diff"]["added"]
    assert [f["severity"] for f in added] == ["ERROR", "ERROR", "ERROR"]
    assert sorted({f["code"] for f in added}) == [
        "CONSTRAINT_NOT_UNIQUE",
        "REQUIRED_PROPERTY_MISSING",
    ]
    assert payload["diff"]["removed"] == []
    assert payload["diff"]["summary"]["after"]["ERROR"] == 3


def test_a_value_that_moved_under_one_identity_is_changed_not_replaced() -> None:
    before = [_finding("/a", value="one")]
    after = [_finding("/a", value="two")]
    result = compare(before, after)
    assert result.removed == [] and result.added == []
    assert len(result.changed) == 1
    assert (result.changed[0][0].value, result.changed[0][1].value) == ("one", "two")


def test_a_finding_whose_pointer_shifted_is_reported_as_moved() -> None:
    """An array that gained an element shifts every pointer under it."""
    result = compare([_finding("/links/0")], [_finding("/links/1")])
    assert result.removed == [] and result.added == []
    assert [(b.location, a.location) for b, a in result.moved] == [("/links/0", "/links/1")]
    assert result.ambiguous_moves == []


def test_an_undecidable_move_is_declined_and_said_so() -> None:
    """Two out and two in under one key: which went where is a guess.

    Pairing them arbitrarily would print a settled-looking fact that the
    evidence does not carry, so both stay where they are and the key is named.
    """
    before = [_finding("/links/0"), _finding("/links/1")]
    after = [_finding("/links/5"), _finding("/links/6")]
    result = compare(before, after)
    assert result.moved == []
    assert len(result.removed) == 2 and len(result.added) == 2
    assert result.ambiguous_moves == [("REFERENCE_UNRESOLVED", "href", "x", "c")]


def test_move_pairing_is_off_for_repair_and_the_findings_stay_where_they_were() -> None:
    """``repair --draft`` publishes efficacy numbers over these two categories."""
    result = compare([_finding("/links/0")], [_finding("/links/1")], pair_moves=False)
    assert result.moved == [] and result.ambiguous_moves == []
    assert len(result.removed) == 1 and len(result.added) == 1


def test_repair_and_the_verb_share_one_definition_of_identity() -> None:
    """Not a re-implementation that happens to agree today."""
    from oscal_validate.ai import repair

    assert repair.finding_key is compare_module.finding_key


def test_repair_counts_are_the_comparison_the_verb_runs(tmp_path: Path) -> None:
    """``revalidate``'s numbers reproduce exactly from the shared function.

    The patch is applied directly rather than through a model, so this measures
    the arithmetic and nothing else. It **prepends a control**, which shifts
    every pointer under that array, so the two duplicate-id findings are
    displaced: the case where move pairing would change what ``repair --draft``
    reports. A patch that displaced nothing would make the two settings
    indistinguishable here and the check unable to fail.
    """
    from oscal_validate.ai import repair
    from oscal_validate.ai.run import prepare

    run = prepare(BROKEN, [])
    patched = load_fixture("broken_catalog.json")
    patched["catalog"]["groups"][0]["controls"].insert(0, {"id": "ex-zero", "title": "Zero"})
    outcome = repair.revalidate(run, patched)

    after_path = write(tmp_path, "patched.json", patched)
    after = validate_file(after_path, [])
    expected = compare(run.findings, after, pair_moves=False)
    assert [f.to_dict() for f in outcome.introduced] == [f.to_dict() for f in expected.added]
    assert [f.to_dict() for f in outcome.also_resolved] == [f.to_dict() for f in expected.removed]
    assert outcome.unchanged == expected.unchanged
    assert outcome.before == expected.before and outcome.after == expected.after

    # The witness: this patch really does displace findings, so the two
    # settings disagree, and repair is on the one that keeps its categories.
    paired = compare(run.findings, after, pair_moves=True)
    assert paired.moved, "this patch must displace a finding for the check to bite"
    assert len(outcome.also_resolved) == len(expected.removed) > len(paired.removed)
    assert len(outcome.introduced) == len(expected.added) > len(paired.added)


# -- what a removed finding is, and is not -----------------------------------


def test_a_removed_finding_is_never_called_resolved(capsys: pytest.CaptureFixture[str]) -> None:
    """The whole reason this module exists rather than reusing repair's words.

    Two finding lists cannot tell a repair from a run that read a different
    document, used a different resolve set, or could not get far enough to
    report anything. ``repair --draft`` may say "resolved" because it made the
    edit itself and knows what changed; a diff over two files does not.
    """
    code, out = _run(capsys, str(BROKEN), str(CLEAN))
    assert code == 0
    assert "removed: present before, absent after (3)" in out
    # Only this command's own words are in scope. A rule citation quotes NIST's
    # file names, one of which is oscal_catalog_metaschema_RESOLVED.xml, and
    # those lines are indented; the headings and the summary are not.
    said = [line for line in out.splitlines() if line and not line.startswith(" ")]
    assert said, "no unindented output to check"
    assert not any("resolved" in line.lower() for line in said), said
    assert "it is not evidence that it was fixed" in out


def test_an_after_side_with_no_findings_does_not_read_as_a_clean_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The complement: everything gone must not look like everything fixed.

    An empty report is exactly what a truncated or failed run produces, and it
    is indistinguishable here from a perfect one. So the diff reports eight
    removals and says what a removal is worth, and the after-summary shows the
    zero it is actually looking at.
    """
    empty = tmp_path / "empty-report.json"
    empty.write_text(
        json.dumps(
            {
                "tool": {"name": "oscal-validate", "version": "9.9.9"},
                "document": {"model": "catalog"},
                "findings": [],
                "summary": {},
            }
        ),
        encoding="utf-8",
    )
    code, out = _run(capsys, str(BROKEN), str(empty))
    assert code == 0
    assert "removed: present before, absent after (8)" in out
    assert "after: 0 finding(s): 0 ERROR, 0 WARNING, 0 INFO, 0 UNVERIFIABLE" in out
    assert "it is not evidence that it was fixed" in out


# -- provenance the inputs cannot supply -------------------------------------


def test_a_report_from_another_tool_version_diffs_with_a_stated_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = _report(tmp_path, "old.json", CLEAN, version="0.0.1")
    code, out = _run(capsys, str(saved), str(CLEAN))
    assert code == 0
    assert "tool version differs: 0.0.1 ->" in out
    assert "because the tool changed" in out


def test_a_saved_report_does_not_know_which_snapshot_produced_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Absence stated, not passed over.

    A report records the tool version and nothing about the vendored schema, so
    two reports can be compared with no way to know whether the same schema was
    behind them. Printing the release for the validated side and nothing for
    the other would invite the reader to assume they matched.
    """
    saved = _report(tmp_path, "saved.json", CLEAN)
    code, out = _run(capsys, str(saved), str(CLEAN))
    assert code == 0
    assert "vendored OSCAL snapshot unknown for saved.json" in out
    assert "cannot be determined here" in out


def test_two_validated_sides_carry_the_snapshot_and_raise_no_note(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The note must not fire when both sides do know, or it says nothing."""
    code, out = _run(capsys, str(CLEAN), str(BROKEN), "--format", "json")
    assert code == 0
    payload = json.loads(out)
    assert payload["notes"] == []
    assert payload["before"]["oscal_snapshot"] == payload["after"]["oscal_snapshot"] != ""
    assert payload["before"]["origin"] == "document"


# -- what a `changed` entry shows -------------------------------------------
#
# Found by the coverage misses rather than by the suite. `render_text`'s
# `changed` and `moved` loop bodies and its `ambiguous_moves` line had never
# executed: every test above reads the comparison or the JSON, and the text
# report's own words for those three were unproven. One of them was wrong.


def test_a_message_only_change_shows_the_message(capsys: pytest.CaptureFixture[str]) -> None:
    """The defect. Reproduced on unmodified `main` before it was fixed.

    `IDENTITY` deliberately leaves value and message out, so a finding whose
    sentence was corrected is `changed`. The entry printed `_line(new)` --
    which carries no message -- and `was: <value> / <severity>`, so both
    halves of the entry were identical on every byte shown. The heading said a
    finding had changed and the block under it showed nothing that had.

    Not hypothetical: two of the seven golden re-captures in
    `tests/test_default_path_byte_identity.py` are message-only changes.
    """
    before = _finding("/a")
    after = dataclasses.replace(before, message="a different sentence about the same defect")
    rendered = render_text(_side(before), _side(after), compare([before], [after]))

    assert "changed: same finding, different value or message (1)" in rendered
    assert "message was: m" in rendered
    assert "message now: a different sentence about the same defect" in rendered


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("value", "two", ("value was: x", "value now: two")),
        ("severity", Severity.WARNING, ("severity was: ERROR", "severity now: WARNING")),
        ("message", "n", ("message was: m", "message now: n")),
    ],
)
def test_every_field_that_differs_is_named_on_both_sides(
    field: str, value: Any, expected: tuple[str, str]
) -> None:
    before = _finding("/a")
    after = dataclasses.replace(before, **{field: value})
    rendered = render_text(_side(before), _side(after), compare([before], [after]))
    for line in expected:
        assert line in rendered
    # And only the field that moved: a block naming three differences where
    # one exists is as unreadable as a block naming none.
    named = {line.split(" was:")[0].strip() for line in rendered.splitlines() if " was:" in line}
    assert named == {field}


def test_a_rule_that_was_re_retrieved_is_named_as_the_difference() -> None:
    """`Rule` carries the date its source was read, and that is outside
    `IDENTITY` on purpose -- so a re-retrieval makes a `changed` pair whose
    finding text is word for word what it was."""
    before = _finding("/a")
    after = dataclasses.replace(before, rule=Rule(citation="c", url="u", retrieved="2026-09-10"))
    rendered = render_text(_side(before), _side(after), compare([before], [after]))
    assert "rule source was: u (retrieved -)" in rendered
    assert "rule source now: u (retrieved 2026-09-10)" in rendered


def test_a_change_in_a_field_the_report_does_not_show_says_so() -> None:
    """The floor. `compare` pairs on inequality as values, so a pair can differ
    in a field this renderer has no line for -- `suggestions`, or the source
    position `--locations` attaches. Printing an empty block under a heading
    that says something changed is the same defect one level down, so the
    entry states which fields it compared and points at the format that
    carries both findings whole."""
    before = _finding("/a")
    after = dataclasses.replace(before, position=Position(file="f.json", line=3, column=1))

    result = compare([before], [after])
    assert len(result.changed) == 1, "the pair must reach `changed` or this proves nothing"

    rendered = render_text(_side(before), _side(after), result)
    assert "reported as changed, and value, severity, message" in rendered
    assert "--format json carries both findings whole" in rendered
    assert " was:" not in rendered


# -- the other two loop bodies, and the note that cannot fire yet ------------


def test_a_moved_finding_names_where_it_was(capsys: pytest.CaptureFixture[str]) -> None:
    rendered = render_text(
        _side(_finding("/links/0")),
        _side(_finding("/links/1")),
        compare([_finding("/links/0")], [_finding("/links/1")]),
    )
    assert "moved: same code, property, value and rule at a different location (1)" in rendered
    assert "was at: /links/0" in rendered
    assert "at=/links/1" in rendered


def test_an_undecidable_move_is_declined_in_the_text_report_too() -> None:
    """`test_an_undecidable_move_is_declined_and_said_so` holds the data model.
    This holds the sentence a reader actually sees, which had never run."""
    before = [_finding("/links/0"), _finding("/links/1")]
    after = [_finding("/links/5"), _finding("/links/6")]
    rendered = render_text(_side(*before), _side(*after), compare(before, after))
    assert "not paired: several findings removed and several added for" in rendered
    assert "which moved where is not decidable" in rendered
    assert "counted above as removed and added" in rendered


def test_two_different_known_snapshots_are_reported_as_differing() -> None:
    """This branch cannot fire through the CLI today and is tested anyway.

    `load_side` gives a validated side `OSCAL_RELEASE` and a saved report
    `UNRECORDED`, so two sides with two *known* and different snapshots need a
    report format that records one. The sentence is written for that day; a
    sentence that has never executed is not one anybody can rely on arriving
    correct when the data finally reaches it.
    """
    before = dataclasses.replace(_side(_finding("/a")), snapshot="1.2.2")
    after = dataclasses.replace(_side(_finding("/a")), snapshot="1.2.3")
    assert provenance_notes(before, after) == ["vendored OSCAL snapshot differs: 1.2.2 -> 1.2.3."]
    # And it must not fire when they agree, or it says nothing.
    assert provenance_notes(before, before) == []


# -- exit codes --------------------------------------------------------------


def test_a_diff_exits_zero_whatever_it_found(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(capsys, str(CLEAN), str(BROKEN))[0] == 0


def test_fail_on_new_gates_on_a_newly_added_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(capsys, str(CLEAN), str(BROKEN), "--fail-on-new")[0] == 1
    # The same three ERRORs going the other way are removals, not new ones.
    assert _run(capsys, str(BROKEN), str(CLEAN), "--fail-on-new")[0] == 0


def test_fail_on_new_ignores_a_new_finding_that_is_not_an_error() -> None:
    """It gates on ERROR, and an added WARNING is not one."""
    warning = Finding(
        code="OSCAL_VERSION_DIFFERS",
        severity=Severity.WARNING,
        location="/catalog/metadata/oscal-version",
        prop="oscal-version",
        value="1.1.2",
        message="m",
        rule=Rule(citation="c", url="u", retrieved="-"),
    )
    assert compare([], [warning]).new_errors == []
    assert compare([], [_finding("/a")]).new_errors


def test_an_unreadable_input_is_exit_two_with_no_diff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "not.json"
    broken.write_text("{ not json", encoding="utf-8")
    code, out = _run(capsys, str(broken), str(CLEAN))
    assert code == 2 and out == ""
    code, out = _run(capsys, str(tmp_path / "absent.json"), str(CLEAN))
    assert code == 2 and out == ""


def test_a_malformed_report_is_refused_rather_than_partly_read(tmp_path: Path) -> None:
    """A partial read of evidence is the thing this comparison must not publish."""
    payload: Any = {
        "tool": {"name": "oscal-validate", "version": "1"},
        "findings": [
            {
                "code": "X",
                "severity": "ERROR",
                "location": "/a",
                "property": "p",
                "value": "v",
                "message": "m",
                "rule": {"citation": "c", "url": "u", "retrieved": "-"},
            },
            {"code": "Y"},
        ],
    }
    with pytest.raises(ReportError, match="finding 1"):
        findings_from_report(payload)
    payload["findings"][1]["severity"] = "NOT_A_SEVERITY"
    payload["findings"][1].update(
        {
            "location": "/b",
            "property": "p",
            "value": "v",
            "message": "m",
            "rule": {"citation": "c", "url": "u", "retrieved": "-"},
        }
    )
    with pytest.raises(ReportError, match="finding 1"):
        findings_from_report(payload)


def test_resolve_against_a_saved_report_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A report's findings were produced under its own run's resolve set."""
    saved = _report(tmp_path, "saved.json", CLEAN)
    code, out = _run(capsys, str(saved), str(CLEAN), "--resolve-before", str(CLEAN))
    assert code == 2 and out == ""


def test_a_resolve_set_reaches_the_side_it_names(capsys: pytest.CaptureFixture[str]) -> None:
    """Otherwise the two sides would silently be validated the same way."""
    profile = fixture_path("clean_profile.json")
    code, out = _run(capsys, str(profile), str(profile), "--resolve-after", str(CLEAN))
    assert code == 0
    assert "IMPORT_NOT_SUPPLIED" in out
    assert "IMPORT_RESOLVED" in out


# -- the same guarantees as the default path ---------------------------------


def test_the_diff_verb_never_imports_the_ai_layer() -> None:
    """It shares a module with ``repair`` and must not drag the SDK in with it."""
    script = (
        "import sys\n"
        "from oscal_validate.cli import main\n"
        f"main(['diff', {str(CLEAN)!r}, {str(BROKEN)!r}])\n"
        "loaded = sorted(m for m in sys.modules if m.startswith(('oscal_validate.ai', "
        "'anthropic', 'httpx', 'boto')))\n"
        "print(loaded)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "[]"


def test_the_verb_is_deterministic(capsys: pytest.CaptureFixture[str]) -> None:
    first = _run(capsys, str(CLEAN), str(BROKEN), "--format", "json")[1]
    second = _run(capsys, str(CLEAN), str(BROKEN), "--format", "json")[1]
    assert first == second


def test_the_fixtures_this_file_relies_on_are_present() -> None:
    """A file-not-found would make several assertions above pass vacuously."""
    assert FIXTURES.is_dir()
    for path in (CLEAN, BROKEN):
        assert path.is_file(), path


def test_every_deterministic_command_is_actually_dispatched() -> None:
    """The tuple and the dispatch branches cannot drift apart.

    Each verb is imported by a literal module path rather than by interpolating
    the argument, so the tuple is not what routes the call and a name could be
    listed here while falling through to the default parser -- which takes a
    file as its first positional and would report the verb as a missing file.
    ``--help`` exits 0 from the verb's own parser and 2 from the default one.
    """
    assert DETERMINISTIC_COMMANDS, "an empty tuple would make this pass vacuously"
    for verb in DETERMINISTIC_COMMANDS:
        with pytest.raises(SystemExit) as exit_info:
            main([verb, "--help"])
        assert exit_info.value.code == 0, verb


def test_a_word_that_is_not_a_verb_is_still_read_as_a_filename(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dispatch must not swallow a path that happens to sit in first position."""
    assert main(["diffusion-report.json"]) == 2
    assert "diffusion-report.json" in capsys.readouterr().err
