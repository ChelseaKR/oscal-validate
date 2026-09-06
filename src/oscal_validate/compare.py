"""What changed between two runs, as a set comparison over findings.

This is the deterministic half of ``oscal-validate diff``, and it is also what
``repair --draft`` has always used to say "resolves F6; 6 untouched; 1 also
resolved; 0 introduced". There was one implementation of that comparison and it
lived inside the model-backed command; ``ai/repair.py`` now calls this one, so
the verb and the draft cannot disagree about what "introduced" means.

Nothing here validates, reads a file, or calls a model. It takes two lists of
findings and answers one question: which of them are the same finding.

**A finding that is absent from the second run has not necessarily been
fixed.** It is absent, and that is all this module ever says. A run over a
truncated document, a run with a different ``--resolve`` set, or a run whose
schema could not be read produces exactly the same absence as a repair, and
naming the second column "resolved" would be this portfolio's oldest mistake in
a new place. The words used here are ``removed`` and ``added``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .findings import Finding, Rule, Severity, counts

#: The fields that make two findings the same finding across two runs.
#:
#: Code, location and property, plus the rule citation: two constraints can
#: fail at one location on one property -- the catalog's two id indexes do --
#: and the citation is what tells them apart. Value and message are left out so
#: that a finding whose count or quoted value moved is reported as changed
#: rather than as one removed and one added.
IDENTITY = ("code", "location", "prop", "rule.citation")

#: The fields a *moved* finding keeps. Location is deliberately absent: an
#: array that gained an element shifts every pointer under it, and reporting
#: that as a wall of removals and additions buries whatever really changed.
DISPLACED = ("code", "prop", "value", "rule.citation")


def finding_key(finding: Finding) -> tuple[str, str, str, str]:
    """The identity of a finding across two runs. See :data:`IDENTITY`."""
    return (finding.code, finding.location, finding.prop, finding.rule.citation)


def _displaced_key(finding: Finding) -> tuple[str, str, str, str]:
    return (finding.code, finding.prop, finding.value, finding.rule.citation)


@dataclass
class Comparison:
    """Two runs, compared. Every list is ordered by the findings' own sort key.

    ``removed`` and ``added`` are named for what the evidence supports. A
    finding present before and absent after was not observed in the second run;
    whether that is because it was fixed, because the second run read a
    different document, or because the second run could not get far enough to
    report it, is not knowable from two finding lists and is not claimed here.
    """

    removed: list[Finding]
    added: list[Finding]
    changed: list[tuple[Finding, Finding]]
    moved: list[tuple[Finding, Finding]]
    unchanged: int
    before: dict[str, int]
    after: dict[str, int]
    #: Non-location keys where several findings were removed and several added,
    #: so which moved where cannot be decided. Their findings stay in
    #: ``removed`` and ``added`` rather than being paired off arbitrarily.
    ambiguous_moves: list[tuple[str, str, str, str]]

    @property
    def empty(self) -> bool:
        return not (self.removed or self.added or self.changed or self.moved)

    @property
    def new_errors(self) -> list[Finding]:
        """Added findings at ERROR. A moved ERROR is not a new one."""
        return [f for f in self.added if f.severity is Severity.ERROR]

    def to_dict(self) -> dict[str, Any]:
        return {
            "removed": [f.to_dict() for f in self.removed],
            "added": [f.to_dict() for f in self.added],
            "changed": [{"before": b.to_dict(), "after": a.to_dict()} for b, a in self.changed],
            "moved": [{"before": b.to_dict(), "after": a.to_dict()} for b, a in self.moved],
            "unchanged": self.unchanged,
            "summary": {"before": self.before, "after": self.after},
            "ambiguous_moves": [
                dict(zip(DISPLACED, key, strict=True)) for key in self.ambiguous_moves
            ],
        }


def _pair_moves(
    removed: list[Finding], added: list[Finding]
) -> tuple[list[tuple[Finding, Finding]], list[Finding], list[Finding], list[tuple[str, ...]]]:
    """Match a removal to an addition that differs only in location.

    Only where the match is unambiguous: exactly one removed and exactly one
    added finding share the non-location key. Where several share it, which
    went where is a guess, and a guess presented as a move would read as a
    settled fact. Those stay in ``removed`` and ``added``, and the key is
    reported so the reader knows the pairing was declined rather than missed.
    """
    from_before: dict[tuple[str, ...], list[Finding]] = defaultdict(list)
    from_after: dict[tuple[str, ...], list[Finding]] = defaultdict(list)
    for finding in removed:
        from_before[_displaced_key(finding)].append(finding)
    for finding in added:
        from_after[_displaced_key(finding)].append(finding)

    moved: list[tuple[Finding, Finding]] = []
    ambiguous: list[tuple[str, ...]] = []
    paired: set[int] = set()
    for key in sorted(set(from_before) & set(from_after)):
        before_side, after_side = from_before[key], from_after[key]
        if len(before_side) == 1 and len(after_side) == 1:
            moved.append((before_side[0], after_side[0]))
            paired.add(id(before_side[0]))
            paired.add(id(after_side[0]))
        else:
            ambiguous.append(key)
    moved.sort(key=lambda pair: pair[1].sort_key())
    return (
        moved,
        [f for f in removed if id(f) not in paired],
        [f for f in added if id(f) not in paired],
        ambiguous,
    )


def compare(before: list[Finding], after: list[Finding], *, pair_moves: bool = True) -> Comparison:
    """Compare two runs' findings.

    Identity is :data:`IDENTITY`. A finding whose value or message moved under
    the same identity is ``changed``. A finding that differs only in location,
    and only where the match is unambiguous, is ``moved``. Everything else is
    ``removed`` or ``added``, in those words.

    ``pair_moves=False`` leaves ``moved`` empty and every displaced finding in
    ``removed`` and ``added``. ``repair --draft`` asks for that: its published
    efficacy numbers count "also resolved" and "introduced", and folding a
    displaced finding into a third category would change what those numbers
    mean without anyone deciding to. The set arithmetic and the definition of
    identity are shared either way, which is the part that must not drift.
    """
    first = {finding_key(f): f for f in before}
    second = {finding_key(f): f for f in after}
    removed = sorted((first[k] for k in first if k not in second), key=Finding.sort_key)
    added = sorted((second[k] for k in second if k not in first), key=Finding.sort_key)
    changed = sorted(
        ((first[k], second[k]) for k in first if k in second and first[k] != second[k]),
        key=lambda pair: pair[1].sort_key(),
    )
    unchanged = sum(1 for k in first if k in second and first[k] == second[k])
    moved: list[tuple[Finding, Finding]] = []
    ambiguous: list[tuple[str, ...]] = []
    if pair_moves:
        moved, removed, added, ambiguous = _pair_moves(removed, added)
    return Comparison(
        removed=removed,
        added=added,
        changed=changed,
        moved=moved,
        unchanged=unchanged,
        before=counts(before),
        after=counts(after),
        ambiguous_moves=[tuple(key) for key in ambiguous],  # type: ignore[misc]
    )


class ReportError(Exception):
    """A file that claims to be a saved report but cannot be read as one."""


def is_report(payload: Any) -> bool:
    """Whether a parsed JSON file is one of this tool's own JSON reports.

    An OSCAL document has exactly one root key naming a model; a report has
    ``tool`` and ``findings`` at the top. Nothing here guesses from a file
    name.
    """
    return isinstance(payload, dict) and "tool" in payload and "findings" in payload


def findings_from_report(payload: Any) -> list[Finding]:
    """Rebuild findings from a saved ``--format json`` report.

    Suggestions are dropped. They are ``--suggest`` output about identifiers
    that *are* declared, not part of what the finding says, and they are
    already outside :data:`IDENTITY`; dropping them on both sides is what stops
    a report captured with the flag from comparing unequal to one captured
    without it, which would report a change that was in the invocation rather
    than in the document.

    A malformed report raises rather than yielding the findings it could read.
    A partial read of evidence is the thing this whole comparison is meant not
    to publish.
    """
    if not is_report(payload):
        raise ReportError("not a saved oscal-validate JSON report")
    rebuilt: list[Finding] = []
    for index, entry in enumerate(payload["findings"]):
        try:
            rule = entry["rule"]
            rebuilt.append(
                Finding(
                    code=str(entry["code"]),
                    severity=Severity(entry["severity"]),
                    location=str(entry["location"]),
                    prop=str(entry["property"]),
                    value=str(entry["value"]),
                    message=str(entry["message"]),
                    rule=Rule(
                        citation=str(rule["citation"]),
                        url=str(rule["url"]),
                        retrieved=str(rule["retrieved"]),
                    ),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ReportError(f"finding {index} in this report is not readable: {exc}") from exc
    return rebuilt


__all__ = [
    "DISPLACED",
    "IDENTITY",
    "Comparison",
    "ReportError",
    "compare",
    "finding_key",
    "findings_from_report",
    "is_report",
]
