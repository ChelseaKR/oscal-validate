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

from collections.abc import Iterator

from .. import rules
from ..document import Scalar, Walked
from ..findings import Finding, Severity
from ..session import Session

UUID_DATATYPE = "UUIDDatatype"


def uuid_definitions(walked: Walked) -> Iterator[Scalar]:
    """Every position in a document that *declares* a UUID, in walk order.

    The one definition of the question, because two callers ask it: this check
    compares declarations within one document, and package mode compares them
    across documents. Two copies of the predicate is how "a UUID definition"
    comes to mean one thing inside a file and another across a directory.
    """
    for scalar in walked.scalars:
        if (
            scalar.datatype == UUID_DATATYPE
            and scalar.name == "uuid"
            and isinstance(scalar.value, str)
        ):
            yield scalar


def check(session: Session) -> list[Finding]:
    seen: dict[str, str] = {}
    findings: list[Finding] = []
    for scalar in uuid_definitions(session.corpus.primary.walked):
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
