"""``--baseline``: every way it is allowed to weaken the gate, and every way it is not.

A baseline is the standard way to make a validator usable on a document nobody
can fix, and it is also the standard way to build a gate that lies. So the
tests here are mostly refusals. Each one drives a path in
:mod:`oscal_validate.baseline` that decides whether a finding stops gating, and
the fixture for every acknowledgement is a **real finding this tool produced**
rather than a hand-written key: a key written by hand would still match itself
after the code that builds it changed, which is the one thing this file must
not be able to do.

The document under all of them is ``broken_catalog.json``, whose findings
include an ERROR (a duplicated identifier) and several UNVERIFIABLE ones. Both
are needed: the ERROR is the thing an acknowledgement is for, and the
UNVERIFIABLE is the thing it must refuse.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from oscal_validate import baseline, validate_file
from oscal_validate import findings as findings_module
from oscal_validate.baseline import BASELINE_VERSION, Baseline, BaselineError, Entry
from oscal_validate.cli import main
from oscal_validate.findings import Finding, Severity, counts
from oscal_validate.htmlreport import render_findings_html

from .conftest import fixture_path

DOCUMENT = "broken_catalog.json"

#: A reason and a date that would be written by a person. Nothing in the module
#: compares the date against today, and ``test_nothing_here_reads_the_clock``
#: is what holds it to that.
REASON = "NIST publishes this catalog with the duplicate; we cannot edit their file"
ACKNOWLEDGED_ON = "2026-09-07"


def _findings() -> list[Finding]:
    return validate_file(fixture_path(DOCUMENT))


def _first(severity: Severity) -> Finding:
    for finding in _findings():
        if finding.severity is severity:
            return finding
    raise AssertionError(f"{DOCUMENT} produces no {severity.value} finding to build an entry from")


def _row(finding: Finding, **overrides: Any) -> dict[str, Any]:
    """A baseline entry naming a finding this run really produced."""
    row: dict[str, Any] = {
        "code": finding.code,
        "location": finding.location,
        "property": finding.prop,
        "value": finding.value,
        "reason": REASON,
        "acknowledged_on": ACKNOWLEDGED_ON,
    }
    row.update(overrides)
    return row


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per key, which is what a baseline file is allowed to hold."""
    seen: set[tuple[str, str, str, str]] = set()
    kept: list[dict[str, Any]] = []
    for row in rows:
        key = (row["code"], row["location"], row["property"], row["value"])
        if key not in seen:
            seen.add(key)
            kept.append(row)
    return kept


def _error_rows() -> list[dict[str, Any]]:
    """One row per distinct key among this document's ERROR findings.

    Distinct keys, not distinct findings: two of them share a key, and a file
    holding both is refused. That is the same shape ``--write-baseline``
    produces, and it is asserted directly in
    ``test_write_baseline_writes_one_entry_per_key``.
    """
    return _dedupe([_row(f) for f in _findings() if f.severity is Severity.ERROR])


def _file(tmp_path: Path, *rows: dict[str, Any], version: str = BASELINE_VERSION) -> Path:
    path = tmp_path / "oscal-baseline.json"
    path.write_text(
        json.dumps({"baseline_version": version, "entries": list(rows)}, indent=2),
        encoding="utf-8",
    )
    return path


def _write(tmp_path: Path, payload: Any) -> Path:
    path = tmp_path / "oscal-baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# What an acknowledgement changes, and what it must leave alone
# --------------------------------------------------------------------------


def test_an_acknowledged_error_keeps_its_severity_its_place_and_its_count(
    tmp_path: Path,
) -> None:
    """The whole promise of this feature, asserted as separate facts.

    Any one of them failing turns a baseline from "we have looked at this and
    accepted it" into "we have hidden this", which is the substitution the
    module exists to refuse.
    """
    before = _findings()
    error = _first(Severity.ERROR)
    key = (error.code, error.location, error.prop, error.value)
    after = baseline.apply(before, baseline.load(_file(tmp_path, _row(error))))

    acknowledged = [f for f in after if f.acknowledged is not None]
    named = [f for f in before if (f.code, f.location, f.prop, f.value) == key]
    assert named, "the fixture must produce the finding this entry names"
    assert len(acknowledged) == len(named)
    for marked in acknowledged:
        assert marked.severity is Severity.ERROR
        assert marked.code == error.code
        assert marked.acknowledged is not None
        assert marked.acknowledged.reason == REASON
        assert marked.acknowledged.acknowledged_on == ACKNOWLEDGED_ON
        assert marked.gates is False
    # Messages are untouched, including where two findings share one key.
    assert [f.message for f in acknowledged] == [f.message for f in named]
    # Same findings, same order, same counts. Only the flag moved.
    assert [f.code for f in after] == [f.code for f in before]
    assert counts(after) == counts(before)
    assert error.gates is True


def test_one_entry_acknowledges_every_finding_its_key_names(tmp_path: Path) -> None:
    """A key is not always one finding, and the two halves must agree about it.

    ``broken_catalog.json`` reports the same duplicated identifier under two
    different NIST constraints: same code, same location, same property, same
    value, different message and different rule. ``KEY_FIELDS`` excludes the
    message deliberately, so one entry covers both -- and the generator has to
    write one entry for them, or it emits a file ``load`` refuses as duplicated.
    """
    before = _findings()
    collisions = {
        key
        for key in ((f.code, f.location, f.prop, f.value) for f in before)
        if sum(1 for f in before if (f.code, f.location, f.prop, f.value) == key) > 1
    }
    assert collisions, "this fixture no longer exercises the case; find one that does"
    code, location, prop, value = next(iter(collisions))
    row = {
        "code": code,
        "location": location,
        "property": prop,
        "value": value,
        "reason": REASON,
        "acknowledged_on": ACKNOWLEDGED_ON,
    }
    after = baseline.apply(before, baseline.load(_file(tmp_path, row)))
    covered = [f for f in after if f.acknowledged is not None]
    assert len(covered) > 1
    assert len({f.message for f in covered}) == len(covered)
    # And no BASELINE_STALE: the entry matched, more than once.
    assert not [f for f in after if f.code == "BASELINE_STALE"]


def test_an_acknowledged_error_does_not_gate_and_an_unacknowledged_one_still_does(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = str(fixture_path(DOCUMENT))
    error = _first(Severity.ERROR)

    every = _file(tmp_path, *_error_rows())
    assert main([document, "--baseline", str(every)]) == 0
    out = capsys.readouterr().out
    assert "ACKNOWLEDGED" in out
    # Still printed, still an ERROR, still in the count.
    assert error.code in out
    assert "3 ERROR" in out, "an acknowledged ERROR is still counted as one"

    # Drop one of them and the run gates again, on the one nobody acknowledged.
    partial = tmp_path / "partial.json"
    partial.write_text(
        json.dumps({"baseline_version": BASELINE_VERSION, "entries": _error_rows()[:-1]}),
        encoding="utf-8",
    )
    assert main([document, "--baseline", str(partial)]) == 1


def test_a_run_with_no_baseline_writes_the_bytes_it_always_wrote(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The flag is opt-in output, so its absence is the absence of a key.

    ``baseline`` in the JSON report and the baseline line in the text report
    are both absent, and absent is not the same as a baseline that
    acknowledged nothing: a run never given one makes no claim either way.
    """
    document = str(fixture_path(DOCUMENT))
    assert main([document, "--format", "json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert "baseline" not in report
    assert all("acknowledged" not in finding for finding in report["findings"])
    assert main([document]) == 1
    assert "baseline" not in capsys.readouterr().out


def test_the_json_report_derives_its_baseline_counts_from_the_findings_it_shows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    error = _first(Severity.ERROR)
    others = [f for f in _findings() if f.severity is Severity.ERROR and f.code != error.code]
    assert others, "the fixture needs a second, unacknowledged ERROR for the exit code below"
    rows = [_row(f) for f in _findings() if f.severity is Severity.ERROR]
    path = _file(tmp_path, *_dedupe(rows), _row(error, location="/catalog/nowhere"))
    assert main([str(fixture_path(DOCUMENT)), "--format", "json", "--baseline", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["baseline"]["path"] == str(path)
    assert report["baseline"]["stale"] == 1
    shown = [f for f in report["findings"] if "acknowledged" in f]
    assert len(shown) == report["baseline"]["acknowledged"]
    assert shown[0]["acknowledged"] == {"reason": REASON, "acknowledged_on": ACKNOWLEDGED_ON}
    stale = [f for f in report["findings"] if f["code"] == "BASELINE_STALE"]
    assert len(stale) == report["baseline"]["stale"]


def test_the_html_report_shows_the_acknowledgement_and_stops_claiming_the_error_gates(
    tmp_path: Path,
) -> None:
    """The page a person signs off from must agree with the exit code.

    Its summary used to answer "yes" in the gating column for ERROR
    unconditionally -- true until ``--baseline`` existed, and a claim that the
    run failed a gate it passes for every run given one.
    """
    error = _first(Severity.ERROR)

    # 1. No baseline: the page reads exactly as it always did.
    without = render_findings_html(_findings(), "0.0.0", "catalog", fixture_path(DOCUMENT))
    assert "Acknowledged" not in without
    assert "Baseline:" not in without
    assert "<td>yes</td>" in without, "ERROR gates when nothing acknowledged it"

    # 2. Some acknowledged, some not: the column has to say which.
    partial = _file(tmp_path, *_error_rows()[:-1])
    page = render_findings_html(
        baseline.apply(_findings(), baseline.load(partial)),
        "0.0.0",
        "catalog",
        fixture_path(DOCUMENT),
        (),
        str(partial),
    )
    assert "Acknowledged 2026-09-07 by the baseline" in page
    assert REASON in page
    assert "still ERROR and still counted in the summary above" in page
    assert "acknowledged by the baseline and not gating" in page
    assert f"Baseline: <code>{partial}</code>" in page
    assert error.location in page
    assert "<td>yes</td>" not in page

    # 3. Every ERROR acknowledged: the run exits 0, and the page must say so
    #    rather than answering "yes" beside a count it no longer describes.
    every = _file(tmp_path, *_error_rows())
    passing = render_findings_html(
        baseline.apply(_findings(), baseline.load(every)),
        "0.0.0",
        "catalog",
        fixture_path(DOCUMENT),
        (),
        str(every),
    )
    assert "no &mdash; all 3 acknowledged by the baseline" in passing
    assert "<td>yes</td>" not in passing
    # The ERROR count itself is untouched: three of them are still on the page.
    assert '<th scope="row">ERROR</th><td>3</td>' in passing


# --------------------------------------------------------------------------
# What a baseline is refused for
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["code", "location", "property", "value", "reason"])
@pytest.mark.parametrize("how", ["missing", "blank", "whitespace"])
def test_an_entry_short_of_a_required_field_is_refused(
    tmp_path: Path, field: str, how: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refused, not defaulted and not warned about.

    ``reason`` is in this list beside the key fields deliberately: an entry
    with no reason is an unexplained exception, which is what a baseline must
    never be able to become.
    """
    row = _row(_first(Severity.ERROR))
    if how == "missing":
        del row[field]
    else:
        row[field] = "" if how == "blank" else "   "
    assert main([str(fixture_path(DOCUMENT)), "--baseline", str(_file(tmp_path, row))]) == 2
    assert field in capsys.readouterr().err


def test_an_entry_naming_an_unverifiable_finding_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """There is nothing to acknowledge in an answer the tool did not reach.

    Keyed on the severity this run produced rather than on a list of codes,
    which would drift the moment a code changed severity.
    """
    unsettled = _first(Severity.UNVERIFIABLE)
    path = _file(tmp_path, _row(unsettled))
    assert main([str(fixture_path(DOCUMENT)), "--baseline", str(path)]) == 2
    message = capsys.readouterr().err
    assert unsettled.code in message
    assert "UNVERIFIABLE" in message
    with pytest.raises(BaselineError, match="UNVERIFIABLE"):
        baseline.apply(_findings(), baseline.load(path))


def test_two_entries_for_one_finding_are_refused(tmp_path: Path) -> None:
    """Two reasons for one finding leave which one applies undetermined."""
    row = _row(_first(Severity.ERROR))
    with pytest.raises(BaselineError, match="same finding"):
        baseline.load(_file(tmp_path, row, dict(row, reason="a different reason")))


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("not json at all", "not valid JSON"),
        ('["a list"]', "top level must be an object"),
        ('{"baseline_version": "1.0.0", "entries": {}}', "entries must be a list"),
        ('{"baseline_version": "1.0.0", "entries": ["a string"]}', "is not an object"),
        ('{"baseline_version": "0.9.0", "entries": []}', "baseline_version"),
        ('{"entries": []}', "baseline_version"),
    ],
)
def test_a_baseline_that_cannot_be_read_is_refused_rather_than_read_as_empty(
    tmp_path: Path, payload: str, expected: str
) -> None:
    """A malformed baseline read as "no entries" would be a file that opens the
    gate it was written to narrow, silently."""
    path = tmp_path / "oscal-baseline.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(BaselineError, match=expected):
        baseline.load(path)


def test_a_baseline_that_is_not_there_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "no-such-baseline.json"
    with pytest.raises(BaselineError):
        baseline.load(missing)
    assert main([str(fixture_path(DOCUMENT)), "--baseline", str(missing)]) == 2
    assert str(missing) in capsys.readouterr().err


@pytest.mark.parametrize(
    "value",
    [
        "20260907",  # the basic form: fromisoformat takes it, YYYY-MM-DD is not it
        "2026-W01-1",  # an ISO week date: same
        "2026-9-7",  # unpadded
        "7 September 2026",
        "2026-02-30",  # well shaped and not a real day
        "2026-13-01",
    ],
)
def test_an_acknowledged_on_that_is_not_a_calendar_date_is_refused(
    tmp_path: Path, value: str
) -> None:
    """``fromisoformat`` alone is not this check.

    Since 3.11 it accepts the basic form and ISO week dates, neither of which
    is the ``YYYY-MM-DD`` the file declares; the pattern alone accepts
    ``2026-02-30``. Both together accept exactly one spelling of exactly the
    real dates.
    """
    row = _row(_first(Severity.ERROR), acknowledged_on=value)
    with pytest.raises(BaselineError, match="acknowledged_on"):
        baseline.load(_file(tmp_path, row))


def test_nothing_here_reads_the_clock(tmp_path: Path) -> None:
    """A verdict that depends on when it runs is not deterministic.

    A future ``acknowledged_on`` is accepted, and that is the documented
    behaviour rather than an oversight: this module never compares the date
    against today, so there is no age check for a future date to satisfy
    forever. The source assertion is what stops that becoming untrue.
    """
    source = (
        Path(__file__).resolve().parent.parent / "src" / "oscal_validate" / "baseline.py"
    ).read_text(encoding="utf-8")
    assert "date.today" not in source
    assert "datetime.now" not in source
    assert "utcnow" not in source
    row = _row(_first(Severity.ERROR), acknowledged_on="2099-01-01")
    loaded = baseline.load(_file(tmp_path, row))
    assert loaded.entries[0].acknowledged_on == "2099-01-01"


# --------------------------------------------------------------------------
# A baseline cannot outlive the defect it excused
# --------------------------------------------------------------------------


def test_an_entry_matching_nothing_is_reported_and_gates_only_when_asked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = str(fixture_path(DOCUMENT))
    row = _row(
        _first(Severity.ERROR),
        location="/catalog/groups/9/controls/9",
        code="TYPE_MISMATCH",
    )
    path = _file(tmp_path, row)

    assert main([document, "--baseline", str(path)]) == 1  # the real ERRORs still gate
    out = capsys.readouterr().out
    assert "BASELINE_STALE" in out
    assert REASON in out, "the stale report has to carry the reason, or nobody can judge it"

    # With every real ERROR acknowledged as well, only the stale entry is left.
    both = _file(tmp_path, row, *_error_rows())
    assert main([document, "--baseline", str(both)]) == 0
    assert main([document, "--baseline", str(both), "--fail-on-stale"]) == 1


def test_the_stale_code_is_the_one_the_renderers_and_the_action_count() -> None:
    """``baseline.py`` spells ``BASELINE_STALE`` as a literal on purpose, so the
    finding-code census can read it. This is the assertion that keeps the
    literal and the constant every counter uses from drifting apart."""
    assert findings_module.BASELINE_STALE == "BASELINE_STALE"
    stale = baseline._stale_finding(
        Path("oscal-baseline.json"),
        Entry(
            finding_code="TYPE_MISMATCH",
            location="/catalog",
            prop="p",
            value="v",
            reason=REASON,
            acknowledged_on=ACKNOWLEDGED_ON,
        ),
    )
    assert stale.code == findings_module.BASELINE_STALE
    assert stale.severity is Severity.WARNING
    assert findings_module.stale_count([stale]) == 1
    assert stale.gates is False


def test_a_stale_finding_carries_no_acknowledgement_of_its_own() -> None:
    """It is a finding *about* the baseline, so acknowledging it would let one
    entry excuse another entry's staleness."""
    stale = baseline.apply(
        [],
        Baseline(
            path=Path("oscal-baseline.json"),
            entries=(
                Entry(
                    finding_code="TYPE_MISMATCH",
                    location="/catalog",
                    prop="p",
                    value="v",
                    reason=REASON,
                    acknowledged_on=ACKNOWLEDGED_ON,
                ),
            ),
        ),
    )
    assert [f.code for f in stale] == ["BASELINE_STALE"]
    assert stale[0].acknowledged is None


# --------------------------------------------------------------------------
# --write-baseline
# --------------------------------------------------------------------------


def test_write_baseline_prints_a_document_that_load_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The generated file is deliberately not usable as generated.

    Every ``reason`` comes out empty, and an empty reason is refused, so the
    file cannot be committed and pointed at without someone writing down why
    each entry is there.
    """
    assert main([str(fixture_path(DOCUMENT)), "--write-baseline"]) == 0
    written = capsys.readouterr().out
    payload = json.loads(written)
    assert payload["baseline_version"] == BASELINE_VERSION
    assert payload["entries"], "a document with findings must generate entries"
    assert all(entry["reason"] == "" for entry in payload["entries"])
    assert all(entry["acknowledged_on"] == "" for entry in payload["entries"])
    with pytest.raises(BaselineError, match="reason"):
        baseline.load(_write(tmp_path, payload))


def test_write_baseline_never_offers_an_unverifiable_finding(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The generator cannot offer what ``load`` would refuse.

    Without this the usual path -- generate, fill in reasons, commit -- would
    hand a person entries the tool then rejects, and the obvious way out of
    that is to relax the refusal.
    """
    assert main([str(fixture_path(DOCUMENT)), "--write-baseline"]) == 0
    offered = {
        (e["code"], e["location"], e["property"], e["value"])
        for e in json.loads(capsys.readouterr().out)["entries"]
    }
    unsettled = {
        (f.code, f.location, f.prop, f.value)
        for f in _findings()
        if f.severity is Severity.UNVERIFIABLE
    }
    assert unsettled, "the fixture must produce UNVERIFIABLE findings or this proves nothing"
    assert not (offered & unsettled)
    gating = {
        (f.code, f.location, f.prop, f.value) for f in _findings() if f.severity is Severity.ERROR
    }
    assert gating <= offered, "an ERROR is the thing a baseline is for; it must be offered"


def test_write_baseline_generates_rather_than_gates(capsys: pytest.CaptureFixture[str]) -> None:
    """Exit 0 whatever the findings were, and no report on stdout: a generator
    whose exit code depended on the document would be unusable in the shell
    pipeline it exists for."""
    assert main([str(fixture_path(DOCUMENT)), "--write-baseline"]) == 0
    out = capsys.readouterr().out
    assert "model:" not in out
    assert "finding(s):" not in out
    json.loads(out)


def test_a_generated_baseline_becomes_usable_once_the_reasons_are_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The end-to-end path, so the two halves cannot drift apart.

    Generate, write a reason and a date into every entry, point ``--baseline``
    at the result: the run reports the same findings and exits 0.
    """
    document = str(fixture_path(DOCUMENT))
    assert main([document, "--write-baseline"]) == 0
    payload = json.loads(capsys.readouterr().out)
    for entry in payload["entries"]:
        entry["reason"] = REASON
        entry["acknowledged_on"] = ACKNOWLEDGED_ON
    path = _write(tmp_path, payload)
    assert main([document, "--baseline", str(path), "--fail-on-stale"]) == 0
    out = capsys.readouterr().out
    assert "0 entry(ies) stale" in out
    # Not one per entry: a key can name more than one finding, and the report
    # counts findings because that is what a reader of the report is looking at.
    settled = [f for f in _findings() if f.severity is not Severity.UNVERIFIABLE]
    assert f"{len(settled)} finding(s) acknowledged" in out


def test_write_baseline_writes_one_entry_per_key_not_one_per_finding(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The generator's output must be a shape ``load`` accepts.

    It was not: it wrote one entry per finding, and two of this document's
    findings share a key, so the file it produced was refused as *duplicated*
    -- a refusal that names the reader for something the generator did, and
    whose only obvious cure is to weaken the duplicate check.
    """
    assert main([str(fixture_path(DOCUMENT)), "--write-baseline"]) == 0
    entries = json.loads(capsys.readouterr().out)["entries"]
    keys = [(e["code"], e["location"], e["property"], e["value"]) for e in entries]
    assert len(keys) == len(set(keys))
    settled = [f for f in _findings() if f.severity is not Severity.UNVERIFIABLE]
    assert len(keys) < len(settled), "this fixture no longer collides; find one that does"
    assert set(keys) == {(f.code, f.location, f.prop, f.value) for f in settled}
