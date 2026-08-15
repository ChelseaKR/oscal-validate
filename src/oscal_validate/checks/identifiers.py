"""Check 4: one UUID, one object, across the whole document.

NIST's constraint layer indexes UUIDs in particular places -- back-matter
resources, metadata parties and locations, SSP components and users -- but it
declares no constraint that a UUID is unique across a document as a whole. The
rule exists all the same, in prose, and it is unambiguous: OSCAL's
machine-oriented UUID identifiers "are always globally-unique". A document in
which two objects carry the same UUID has made a claim that cannot hold, and
every reference to that UUID afterwards is ambiguous.

Only *declaring* positions are compared. A property named ``uuid`` declares an
identifier; the ``-uuid`` reference fields point at one and are checked
elsewhere.
"""

from __future__ import annotations

from .. import rules
from ..findings import Finding, Severity
from ..session import Session

UUID_DATATYPE = "UUIDDatatype"


def check(session: Session) -> list[Finding]:
    seen: dict[str, str] = {}
    findings: list[Finding] = []
    for scalar in session.corpus.primary.walked.scalars:
        if scalar.datatype != UUID_DATATYPE or scalar.name != "uuid":
            continue
        if not isinstance(scalar.value, str):
            continue
        first = seen.setdefault(scalar.value, scalar.pointer)
        if first == scalar.pointer:
            continue
        findings.append(
            Finding(
                code="UUID_NOT_UNIQUE",
                severity=Severity.ERROR,
                location=scalar.pointer,
                prop=scalar.name,
                value=scalar.value,
                message=(
                    f"This UUID already identifies the object at {first}. A UUID in OSCAL "
                    "identifies exactly one object, so a reference to this value cannot "
                    "say which of the two it means."
                ),
                rule=rules.UUID_GLOBALLY_UNIQUE,
            )
        )
    return findings
