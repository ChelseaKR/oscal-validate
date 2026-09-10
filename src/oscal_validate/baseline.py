"""``--baseline``: acknowledge a finding without hiding it.

NIST's own SP 800-53 rev 5 catalog carries an ERROR this tool reports -- a link
naming a statement that does not exist. A team that imports that catalog cannot
fix NIST's file, so their options today are to ignore the exit code or to turn
the gate off. Both end with nobody reading the report.

A baseline is the standard way out, and it is also the standard way to build a
gate that lies. So the rules here are narrow and they are all in one direction:

**An acknowledged finding is still a finding.** It is printed, it keeps its
severity, and it is counted in the summary exactly as it was. The single thing
an acknowledgement changes is whether the finding gates the exit code, and the
report says so on the line beneath it.

**A reason is required, and an entry without one is refused.** Not defaulted,
not warned about -- exit 2, the same as a document that could not be read. A
baseline entry with no reason is an unexplained exception, which is what a
baseline must never be able to become.

**A baseline cannot outlive the defect it excused.** An entry that matches
nothing in this run is reported as ``BASELINE_STALE`` at WARNING, naming the
entry, and ``--fail-on-stale`` makes that gate. Otherwise a baseline written
for a document that has since been fixed keeps standing between the next
reader and a gate that would now pass on its own.

**UNVERIFIABLE cannot be baselined.** There is nothing to acknowledge in an
answer the tool did not reach: acknowledging one would convert "I could not
tell" into "we have decided this is fine", which is the exact substitution
ADR-0002 exists to prevent. An entry matching an UNVERIFIABLE finding is
refused at exit 2, keyed on the severity the run actually produced rather than
on a list of codes that would drift.

**Nothing here reads the clock.** ``acknowledged_on`` is checked for being a
real calendar date and is never compared against today. A tool whose verdict
depends on when it runs is not deterministic, and a date-driven gate goes red
on a calendar rather than on a commit.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import __version__, rules
from .findings import Acknowledgement, Finding, Severity

#: The shape of a baseline file. Its own version, moving independently of the
#: tool's and of the report schema's, because it is a file a team commits.
BASELINE_VERSION = "1.0.0"

#: What identifies one finding for the purpose of acknowledging it. Deliberately
#: not the message: a message is prose this project edits, and an acknowledgement
#: that fell off because a sentence was reworded would silently restore a gate.
#:
#: The consequence, which is real rather than theoretical: **a key does not
#: always name exactly one finding.** ``broken_catalog.json`` reports the same
#: duplicated identifier twice, once under each of two NIST constraints that
#: both forbid it, and the two differ only in their message and their rule. One
#: entry therefore acknowledges both, and that is the honest reading of what a
#: person wrote down -- "we accept this value at this place" is a statement
#: about the value, not about which constraint noticed it first. Both halves of
#: the tool have to agree on that: :func:`render` writes one entry per distinct
#: key, and :func:`apply` marks every finding a key names.
KEY_FIELDS = ("code", "location", "property", "value")

#: Every field an entry must carry. ``reason`` and ``acknowledged_on`` are as
#: required as the key: an entry is an argument, not a suppression.
REQUIRED_FIELDS = (*KEY_FIELDS, "reason", "acknowledged_on")

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class BaselineError(Exception):
    """A baseline that cannot be read or cannot be honoured. Always exit 2."""


Key = tuple[str, str, str, str]


@dataclass(frozen=True)
class Entry:
    #: The finding code this entry acknowledges. Named ``finding_code`` rather
    #: than ``code`` for the reason given on ``CodeGroup`` in ``fixorder.py``:
    #: the AST census enumerates every ``code=`` keyword in the package,
    #: deliberately, and a keyword of that name on a call that builds no
    #: finding enters it as an expression it cannot read. The JSON key stays
    #: ``code``, because that is what a reader of the file sees.
    finding_code: str
    location: str
    prop: str
    value: str
    reason: str
    acknowledged_on: str

    @property
    def key(self) -> Key:
        return (self.finding_code, self.location, self.prop, self.value)

    @property
    def acknowledgement(self) -> Acknowledgement:
        return Acknowledgement(reason=self.reason, acknowledged_on=self.acknowledged_on)

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.finding_code,
            "location": self.location,
            "property": self.prop,
            "value": self.value,
            "reason": self.reason,
            "acknowledged_on": self.acknowledged_on,
        }


@dataclass(frozen=True)
class Baseline:
    path: Path
    entries: tuple[Entry, ...]

    @property
    def by_key(self) -> dict[Key, Entry]:
        return {entry.key: entry for entry in self.entries}


def key_of(finding: Finding) -> Key:
    return (finding.code, finding.location, finding.prop, finding.value)


def load(path: Path) -> Baseline:
    """Read and validate a baseline file, or raise :class:`BaselineError`."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BaselineError(f"{path}: {exc.strerror or exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BaselineError(f"{path}: not valid JSON ({exc})") from exc
    if not isinstance(payload, dict):
        raise BaselineError(f"{path}: the top level must be an object")
    declared = payload.get("baseline_version")
    if declared != BASELINE_VERSION:
        raise BaselineError(
            f"{path}: baseline_version is {declared!r}; this tool reads "
            f"{BASELINE_VERSION!r}. Regenerate it with --write-baseline."
        )
    rows = payload.get("entries")
    if not isinstance(rows, list):
        raise BaselineError(f"{path}: entries must be a list")
    entries = tuple(_entry(path, index, row) for index, row in enumerate(rows))
    _refuse_duplicates(path, entries)
    return Baseline(path=path, entries=entries)


def _entry(path: Path, index: int, row: object) -> Entry:
    where = f"{path}: entry {index}"
    if not isinstance(row, dict):
        raise BaselineError(f"{where} is not an object")
    for field_name in REQUIRED_FIELDS:
        value = row.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise BaselineError(
                f"{where} has no {field_name}. Every entry needs all of "
                f"{', '.join(REQUIRED_FIELDS)}; a reason that is absent or empty is an "
                "unexplained exception, which is what a baseline must never become."
            )
    acknowledged_on = str(row["acknowledged_on"])
    _refuse_bad_date(where, acknowledged_on)
    return Entry(
        finding_code=str(row["code"]),
        location=str(row["location"]),
        prop=str(row["property"]),
        value=str(row["value"]),
        reason=str(row["reason"]),
        acknowledged_on=acknowledged_on,
    )


def _refuse_bad_date(where: str, value: str) -> None:
    """``acknowledged_on`` must be a calendar date, checked without a clock.

    The regular expression is not redundant beside ``fromisoformat``: since
    3.11 that function also accepts the basic form ``20260907`` and ISO week
    dates, neither of which is the ``YYYY-MM-DD`` this file declares. The two
    together accept exactly one spelling of exactly the real dates.
    """
    if not _ISO_DATE.fullmatch(value):
        raise BaselineError(f"{where}: acknowledged_on {value!r} is not YYYY-MM-DD")
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise BaselineError(f"{where}: acknowledged_on {value!r} is not a real date") from exc


def _refuse_duplicates(path: Path, entries: tuple[Entry, ...]) -> None:
    seen: dict[Key, int] = {}
    for index, entry in enumerate(entries):
        first = seen.setdefault(entry.key, index)
        if first != index:
            raise BaselineError(
                f"{path}: entry {index} acknowledges the same finding as entry {first} "
                f"({entry.finding_code} at {entry.location}). Two reasons for one finding leave "
                "which one applies undetermined."
            )


def render(findings: list[Finding]) -> str:
    """A baseline document for this run, for a human to annotate.

    ``reason`` and ``acknowledged_on`` are written empty on purpose. The file
    as generated is **refused** by :func:`load` for exactly one reason -- every
    entry needs a written reason -- so it cannot be committed and used without
    someone writing down why each entry is there.

    That "exactly one reason" is load-bearing, and the first version of this
    function did not honour it. It wrote one entry per finding, and two
    findings can share a key (see :data:`KEY_FIELDS`), so a generated file was
    refused for *duplicate entries* on a document whose findings collide --
    a refusal that blames the reader for something the generator did, and one
    whose only obvious cure is to relax the duplicate check. One entry per
    distinct key is what :func:`apply` matches on, so it is also the only
    shape that describes what an acknowledgement will do.

    UNVERIFIABLE findings are never written: there is nothing to acknowledge in
    an answer the tool did not reach.
    """
    entries: list[Entry] = []
    written: set[Key] = set()
    for f in findings:
        if f.severity is Severity.UNVERIFIABLE:
            continue
        key = key_of(f)
        if key in written:
            continue
        written.add(key)
        entries.append(
            Entry(
                finding_code=f.code,
                location=f.location,
                prop=f.prop,
                value=f.value,
                reason="",
                acknowledged_on="",
            )
        )
    payload = {
        "baseline_version": BASELINE_VERSION,
        "written_by": f"oscal-validate {__version__} --write-baseline",
        "entries": [entry.to_dict() for entry in entries],
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def apply(findings: list[Finding], baseline: Baseline) -> list[Finding]:
    """Mark the findings a baseline acknowledges and report the entries it did not.

    The returned list holds every finding that was passed in, in the same
    order, with an :class:`Acknowledgement` attached where an entry matched --
    plus one ``BASELINE_STALE`` finding for every entry that matched nothing.
    Nothing is ever removed.
    """
    by_key = baseline.by_key
    matched: set[Key] = set()
    marked: list[Finding] = []
    for finding in findings:
        entry = by_key.get(key_of(finding))
        if entry is None:
            marked.append(finding)
            continue
        _refuse_unverifiable(baseline.path, finding)
        matched.add(entry.key)
        marked.append(_acknowledged_copy(finding, entry.acknowledgement))
    stale = [entry for entry in baseline.entries if entry.key not in matched]
    return marked + [_stale_finding(baseline.path, entry) for entry in stale]


def _acknowledged_copy(finding: Finding, acknowledgement: Acknowledgement) -> Finding:
    """The same finding with an acknowledgement attached, and nothing else moved.

    Named in ``RECONSTRUCTION`` in ``tests/test_finding_code_census.py``: it
    copies a code that already exists rather than originating one, which is
    exactly what that exemption is for.
    """
    return Finding(
        code=finding.code,
        severity=finding.severity,
        location=finding.location,
        prop=finding.prop,
        value=finding.value,
        message=finding.message,
        rule=finding.rule,
        suggestions=finding.suggestions,
        acknowledged=acknowledgement,
        # Copied like every other field. A field left off here is not
        # inherited from anywhere: the copy would silently lose it, and an
        # acknowledged finding would be the one finding in a --locations
        # report with no line number. tests/test_locations.py restores that
        # omission on purpose and goes red on it.
        position=finding.position,
    )


def _refuse_unverifiable(path: Path, finding: Finding) -> None:
    if finding.severity is not Severity.UNVERIFIABLE:
        return
    raise BaselineError(
        f"{path}: an entry acknowledges {finding.code} at {finding.location}, which this "
        "run reported UNVERIFIABLE. There is nothing to acknowledge in an answer the tool "
        "did not reach: acknowledging it would turn 'this could not be settled' into "
        "'this was decided to be acceptable'. Supply the missing document instead."
    )


def _stale_finding(path: Path, entry: Entry) -> Finding:
    # The literal rather than the imported constant, deliberately.
    # ``tests/test_finding_code_census.py`` enumerates every ``code=`` keyword
    # in the package and resolves names bound to a string literal *in the same
    # module*; a name imported from another one is recorded as an expression it
    # could not read, which is the right behaviour for a census that must never
    # silently skip. So the code is spelled here, and
    # ``tests/test_baseline.py`` asserts it is ``findings.BASELINE_STALE``.
    return Finding(
        code="BASELINE_STALE",
        severity=Severity.WARNING,
        location=entry.location,
        prop=entry.prop,
        value=entry.value,
        message=(
            f"{path} acknowledges a {entry.finding_code} finding here, and this run did not "
            f"report one. The recorded reason was: {entry.reason} (acknowledged "
            f"{entry.acknowledged_on}). Either the document was fixed and this entry "
            "should be deleted, or the finding moved and the entry no longer names it. "
            "This is a WARNING because both are possible; --fail-on-stale makes it gate."
        ),
        rule=rules.BASELINE_POLICY,
    )
