"""Check 5: which OSCAL release the document was authored against.

This produces no verdict on the document. It states, in the output, the one
fact a reader needs to interpret every other finding: which release's schema
and constraints the findings above were produced from, and whether that is the
release the document itself names.

A document authored against an earlier OSCAL release is entirely legitimate.
It may nonetheless collect findings here that say more about the gap between
two releases than about the document, and a report that did not say so would be
misleading.
"""

from __future__ import annotations

from .. import rules
from ..findings import Finding, Severity
from ..session import Session


def check(session: Session) -> list[Finding]:
    walked = session.corpus.primary.walked
    declared = [
        scalar
        for scalar in walked.scalars
        if scalar.name == "oscal-version" and scalar.pointer.count("/") == 3
    ]
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
