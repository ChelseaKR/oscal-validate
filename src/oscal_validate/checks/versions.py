"""Check 5: which OSCAL release the document was authored against.

This produces no verdict on the document. It states, in the output, the one
fact a reader needs to interpret every other finding: which release's schema
and constraints the findings above were produced from, and whether that is the
release the document itself names.

A document authored against an earlier OSCAL release is entirely legitimate.
It may nonetheless collect findings here that say more about the gap between
two releases than about the document, and a report that did not say so would be
misleading.

``check`` states the gap. ``skew_flags`` states its consequence for the ERRORs
in the same report, and is the only function here that reads other checks'
findings rather than the document; ``validator.validate`` runs it after them.
Both are records that a question was not settled, never a verdict that an ERROR
is wrong: this tool vendors one schema, so it cannot tell a defect in the
document from a difference between two releases, and saying which it is would
be a guess. See ADR-0008.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .. import rules
from ..findings import Finding, Severity
from ..session import Session


def _declared(session: Session) -> list[Any]:
    """The document's own ``metadata/oscal-version`` scalars.

    The pointer depth pins it to the root assembly's metadata, so a nested
    ``oscal-version`` somewhere else in the document is not mistaken for the
    release the document declares itself to be.
    """
    return [
        scalar
        for scalar in session.corpus.primary.walked.scalars
        if scalar.name == "oscal-version" and scalar.pointer.count("/") == 3
    ]


def check(session: Session) -> list[Finding]:
    declared = _declared(session)
    vendored = rules.OSCAL_RELEASE
    findings: list[Finding] = []
    for scalar in declared:
        value = str(scalar.value)
        if value == vendored:
            continue
        findings.append(
            Finding(
                code="OSCAL_VERSION_DIFFERS",
                severity=Severity.WARNING,
                location=scalar.pointer,
                prop="oscal-version",
                value=value,
                message=(
                    f"The document declares OSCAL {value}. Every finding in this report "
                    f"was produced against the vendored OSCAL {vendored} schema and "
                    "constraint layer, so a difference between the two releases can show "
                    "up here as a finding about the document."
                ),
                rule=rules.OSCAL_VERSION_FIELD,
            )
        )
    return findings


def skew_flags(session: Session, findings: list[Finding]) -> list[Finding]:
    """Name the ERRORs that were not checked against the release the document declares.

    Every finding in a report is produced against the vendored release. While
    every ERROR in the corpus was version-independent -- a duplicate UUID, a
    dangling fragment, a missing timezone are wrong in every OSCAL release --
    ``OSCAL_VERSION_DIFFERS`` alone was enough. The widened corpus produced the
    first ERRORs that turn on the difference: a component definition declaring
    1.1.2 where the shape this tool rejects is the shape 1.1.2 used, and mapping
    collections declaring a release whose schema has no mapping model at all.
    Settling those took two schema fetches and a paragraph of prose per finding,
    by hand, in a write-up -- reproducible by nothing in this repository, and
    invisible to a reader of the report itself.

    This is that check's absence, written down where the reader is. It says how
    many ERRORs there are and under which codes, that no schema for the declared
    release is vendored here, and therefore that whether each of them is also an
    error under that release was not determined. It is INFO because the ERROR it
    qualifies is not in doubt: the ERROR is true of the release it cites, and
    only the second question -- true of the declared release too? -- is open.

    Emitted only where a release is declared *and* differs *and* at least one
    ERROR exists. A document with no ``oscal-version`` at all gets no flag,
    because there is no declared release to be skewed from; the schema requires
    the property, so its absence is already an ERROR of its own.
    """
    vendored = rules.OSCAL_RELEASE
    errors = [finding for finding in findings if finding.severity is Severity.ERROR]
    if not errors:
        return []
    counts = Counter(finding.code for finding in errors)
    named = ", ".join(f"{code} ({counts[code]})" for code in sorted(counts))
    flags: list[Finding] = []
    for scalar in _declared(session):
        value = str(scalar.value)
        if value == vendored:
            continue
        flags.append(
            Finding(
                code="VERSION_SKEW_SUSPECTED",
                severity=Severity.INFO,
                location=scalar.pointer,
                prop="oscal-version",
                value=value,
                message=(
                    f"This report carries {len(errors)} ERROR finding(s), every one of them "
                    f"produced against the vendored OSCAL {vendored} schema and constraint "
                    f"layer: {named}. The document declares OSCAL {value}, and no schema for "
                    f"{value} is vendored here, so whether each of those findings is also an "
                    f"error under {value} was not determined by this run. Reading NIST's "
                    f"published schema for {value} is what settles it. Until that is done, "
                    "the count above is a count of ERRORs against "
                    f"{vendored} and not against {value}."
                ),
                rule=rules.VERSION_SKEW_UNCHECKED,
            )
        )
    return flags
