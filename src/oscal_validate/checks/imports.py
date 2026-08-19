"""Check 0: say what the effective data model actually was.

Every UNVERIFIABLE reference finding in this report rests on a claim about
which documents were in hand, so that claim is reported too. Each import the
document declares appears here with the file it was matched to, or with the
reason it was matched to none.

There are two such reasons and they are not the same reason. Nothing was
supplied for the name, or more than one distinct supplied document answers to
it. Reporting the second as the first told a caller who had already handed the
document over to hand it over again, which is advice that cannot be followed
and, when followed, makes the run worse.

These are INFO findings. They gate nothing; they are the audit trail for the
severities the other checks chose.
"""

from __future__ import annotations

from .. import rules
from ..findings import Finding, Severity
from ..session import Session

_RESOLVED = (
    "Matched to {target}, whose identifiers are part of this document's effective data model."
)

_NOT_SUPPLIED = (
    "No document with this file name was supplied. Identifiers it declares are "
    "outside the effective data model this run could see, so references into it "
    "are reported UNVERIFIABLE rather than as failures. Pass it with --resolve to "
    "settle them."
)

_AMBIGUOUS = (
    "{count} distinct supplied documents answer to this file name ({candidates}), so "
    "which of them this import names cannot be determined and none of their "
    "identifiers were admitted to the effective data model. This is not a missing "
    "document and supplying it again will not help: pass the one file this import "
    "means to --resolve, rather than a directory holding more than one of them."
)


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []
    for edge in session.corpus.edges:
        if edge.resolved:
            code = "IMPORT_RESOLVED"
            message = _RESOLVED.format(target=edge.resolved_to)
        elif edge.ambiguous:
            code = "IMPORT_AMBIGUOUS"
            message = _AMBIGUOUS.format(
                count=len(edge.candidates),
                candidates=", ".join(sorted(edge.candidates)),
            )
        else:
            code = "IMPORT_NOT_SUPPLIED"
            message = _NOT_SUPPLIED
        findings.append(
            Finding(
                code=code,
                severity=Severity.INFO,
                location=edge.pointer,
                prop="href",
                value=edge.href,
                message=message,
                rule=rules.EFFECTIVE_DATA_MODEL,
            )
        )
    return findings
