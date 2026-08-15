"""Check 0: say what the effective data model actually was.

Every UNVERIFIABLE reference finding in this report rests on a claim about
which documents were in hand, so that claim is reported too. Each import the
document declares appears here with the file it was matched to, or with the
fact that nothing was supplied for it.

These are INFO findings. They gate nothing; they are the audit trail for the
severities the other checks chose.
"""

from __future__ import annotations

from .. import rules
from ..findings import Finding, Severity
from ..session import Session


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []
    for edge in session.corpus.edges:
        findings.append(
            Finding(
                code="IMPORT_RESOLVED" if edge.resolved else "IMPORT_NOT_SUPPLIED",
                severity=Severity.INFO,
                location=edge.pointer,
                prop="href",
                value=edge.href,
                message=(
                    f"Matched to {edge.resolved_to}, whose identifiers are part of this "
                    "document's effective data model."
                    if edge.resolved
                    else "No document with this file name was supplied. Identifiers it "
                    "declares are outside the effective data model this run could see, "
                    "so references into it are reported UNVERIFIABLE rather than as "
                    "failures. Pass it with --resolve to settle them."
                ),
                rule=rules.EFFECTIVE_DATA_MODEL,
            )
        )
    return findings
