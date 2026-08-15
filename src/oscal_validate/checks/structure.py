"""Check 1: the document's shape against the vendored JSON Schema.

The schema is the least interesting layer of OSCAL and the one every tool
already checks, so this exists mainly because the walk that produces it is what
tells every other check what a value *is*. Required properties, properties the
schema forbids, JSON type mismatches, and objects no declared alternative
accepts fall out of that walk for free.

The last finding here is the important one: where the walk could not descend,
it says so. An unread subtree is reported UNVERIFIABLE rather than counted as
clean.
"""

from __future__ import annotations

from .. import rules
from ..findings import Finding, Severity
from ..session import Session


def check(session: Session) -> list[Finding]:
    walked = session.corpus.primary.walked
    findings: list[Finding] = []

    for note in walked.missing:
        findings.append(
            Finding(
                code="REQUIRED_PROPERTY_MISSING",
                severity=Severity.ERROR,
                location=note.pointer,
                prop=note.name,
                value="(absent)",
                message=(
                    f"{note.detail} requires a {note.name!r} property and this one does "
                    "not have it."
                ),
                rule=rules.required_property_rule(note.detail, note.name),
            )
        )

    for note in walked.undeclared:
        findings.append(
            Finding(
                code="PROPERTY_UNDECLARED",
                severity=Severity.ERROR,
                location=note.pointer,
                prop=note.name,
                value="(present)",
                message=(
                    f"{note.detail} does not declare a property named {note.name!r}, and "
                    "the schema forbids any property it does not declare. Either the name "
                    "is a typo or the document was authored against a different OSCAL "
                    "release than the one vendored here."
                ),
                rule=rules.undeclared_property_rule(note.detail, note.name),
            )
        )

    for note in walked.no_branch:
        findings.append(
            Finding(
                code="NO_SCHEMA_ALTERNATIVE",
                severity=Severity.ERROR,
                location=note.pointer,
                prop=note.name,
                value="(object)",
                message=note.detail,
                rule=rules.no_alternative_rule(note.name),
            )
        )

    for note in walked.mistyped:
        findings.append(
            Finding(
                code="TYPE_MISMATCH",
                severity=Severity.ERROR,
                location=note.pointer,
                prop=note.name,
                value="(wrong JSON type)",
                message=note.detail,
                rule=rules.type_rule(note.name, note.detail.split("'")[1]),
            )
        )

    for note in walked.unwalked:
        findings.append(
            Finding(
                code="SUBTREE_NOT_READ",
                severity=Severity.UNVERIFIABLE,
                location=note.pointer,
                prop=note.name,
                value="(not read)",
                message=(
                    f"This subtree was not read: {note.detail}. Nothing below it has been "
                    "checked by any rule in this tool, and it is reported rather than "
                    "passed over."
                ),
                rule=rules.NOT_WALKED_POLICY,
            )
        )

    return findings
