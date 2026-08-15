"""Check 2: scalar values against the datatype the schema declares for them.

OSCAL's datatypes carry their own regular expressions in the published schema,
so this check never writes one down. It reads the pattern out of the vendored
snapshot and applies it to the values the walk found at that declaration.

Two patterns in OSCAL 1.2.3 use ECMA-262 Unicode property escapes (``\\p{L}``,
``\\p{N}``) that Python's ``re`` module does not implement. Rather than
substituting a hand-written approximation -- which would be a rule encoded from
memory, and the one thing this tool refuses to do -- values governed by such a
pattern are reported as unchecked, once per datatype, with the count.
"""

from __future__ import annotations

from collections import Counter

from .. import rules
from ..findings import Finding, Severity
from ..session import Session


def check(session: Session) -> list[Finding]:
    walked = session.corpus.primary.walked
    schema = session.schema
    findings: list[Finding] = []
    unchecked: Counter[str] = Counter()

    for scalar in walked.scalars:
        if scalar.datatype is None:
            continue
        datatype = schema.datatypes.get(scalar.datatype)
        if datatype is None or datatype.pattern is None:  # pragma: no cover - see below
            continue
        if not isinstance(scalar.value, str):
            continue
        compiled = datatype.compiled
        if compiled is None:
            unchecked[datatype.name] += 1
            continue
        if compiled.search(scalar.value):
            continue
        if any(scalar.value in values for values in scalar.enums):
            # The schema offers this literal as an alternative to the datatype.
            continue
        findings.append(
            Finding(
                code="DATATYPE_MISMATCH",
                severity=Severity.ERROR,
                location=scalar.pointer,
                prop=scalar.name,
                value=_shorten(scalar.value),
                message=(
                    f"The schema declares this value as {datatype.name} "
                    f"({datatype.description}) and the value does not match the pattern "
                    "that datatype declares."
                ),
                rule=rules.datatype_rule(datatype.name, datatype.description, datatype.pattern),
            )
        )

    for name, count in sorted(unchecked.items()):
        pattern = schema.datatypes[name].pattern or ""
        findings.append(
            Finding(
                code="PATTERN_NOT_CHECKED",
                severity=Severity.UNVERIFIABLE,
                location=f"/{walked.model}",
                prop=name,
                value=f"{count} value(s)",
                message=(
                    f"{count} value(s) declared as {name} were not checked against its "
                    f"pattern {pattern} , because that pattern uses regular-expression "
                    "syntax this tool cannot compile. They are neither passed nor failed."
                ),
                rule=rules.UNCOMPILABLE_PATTERN,
            )
        )

    return findings


def _shorten(value: str, limit: int = 120) -> str:
    return value if len(value) <= limit else f"{value[:limit]}..."
