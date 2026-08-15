"""Check 4: identifier references NIST's constraint layer does not cover.

The published constraints reach the metadata identifiers and the back-matter
resources reached through a handful of specific link relations. They do not
reach the references that matter most to a control baseline: a profile's
``with-id``, an SSP's ``control-id``, a ``param-id``, a ``statement-id``, or a
bare ``#`` fragment on a link with any other relation. NIST states the rule for
all of those in prose rather than in a constraint, and this check enforces the
prose rule, citing it.

The severity turns on one question, and only on that question: was every
document this one imports supplied? NIST defines a reference's reach as the
document's *effective data model*, which includes transitively imported
documents. With all of them in hand, a reference that resolves to nothing is
wrong. Without them, the same reference is unknown, and saying so is the whole
point of the UNVERIFIABLE severity.

This check never fetches an imported document. Supply it on the command line
with ``--resolve`` or accept an UNVERIFIABLE answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import rules
from ..document import Scalar
from ..findings import Finding, Severity
from ..session import Session

#: Schema titles that mark a value as *declaring* an identifier. Read from the
#: vendored schema's own titles; pinned by tests/test_reference_titles.py.
IDENTITY_TITLES = frozenset(
    {
        "Control Identifier",
        "Group Identifier",
        "Parameter Identifier",
        "Part Identifier",
        "Role Identifier",
    }
)


@dataclass(frozen=True)
class ReferenceKind:
    """One reference field, the identifiers it may name, and why."""

    title: str
    targets: frozenset[str]
    what: str


#: Reference fields, keyed by the title the vendored schema gives them.
REFERENCE_KINDS = {
    "Control Identifier Reference": ReferenceKind(
        title="Control Identifier Reference",
        targets=frozenset({"Control Identifier"}),
        what="a control",
    ),
    "Match Controls by Identifier": ReferenceKind(
        title="Match Controls by Identifier",
        targets=frozenset({"Control Identifier"}),
        what="a control in an imported control set",
    ),
    "Parameter ID": ReferenceKind(
        title="Parameter ID",
        targets=frozenset({"Parameter Identifier"}),
        what="a parameter",
    ),
    "Control Statement Reference": ReferenceKind(
        title="Control Statement Reference",
        targets=frozenset({"Part Identifier"}),
        what="a control statement, which is a part",
    ),
}


def _identifiers(session: Session) -> dict[str, set[str]]:
    """Every identifier declared anywhere in the effective data model."""
    declared: dict[str, set[str]] = {title: set() for title in IDENTITY_TITLES}
    declared["uuid"] = set()
    for scalar in session.corpus.scalars():
        if not isinstance(scalar.value, str):
            continue
        if scalar.title in IDENTITY_TITLES:
            declared[scalar.title].add(scalar.value)
        elif scalar.name == "uuid":
            declared["uuid"].add(scalar.value)
    return declared


def check(session: Session) -> list[Finding]:
    declared = _identifiers(session)
    everything = {value for values in declared.values() for value in values}
    complete = session.complete
    findings: list[Finding] = []

    for scalar in session.corpus.primary.walked.scalars:
        if not isinstance(scalar.value, str):
            continue
        kind = REFERENCE_KINDS.get(scalar.title)
        if kind is not None:
            available = {v for title in kind.targets for v in declared.get(title, set())}
            if scalar.value not in available:
                findings.append(_unresolved(scalar, kind.what, complete, session))
        elif scalar.name == "href" and scalar.value.startswith("#"):
            if scalar.value[1:] not in everything:
                findings.append(
                    _unresolved(
                        scalar,
                        "an OSCAL object by its identifier, in this document's effective "
                        "data model",
                        complete,
                        session,
                    )
                )

    return findings


def _unresolved(scalar: Scalar, what: str, complete: bool, session: Session) -> Finding:
    return Finding(
        code="REFERENCE_UNRESOLVED" if complete else "REFERENCE_UNVERIFIABLE",
        severity=Severity.ERROR if complete else Severity.UNVERIFIABLE,
        location=scalar.pointer,
        prop=scalar.name,
        value=str(scalar.value),
        message=(
            f"This names {what}, and no such identifier is declared in the documents "
            "supplied. "
            + (
                "Every document named by an import was supplied, so the effective data "
                "model is complete and this reference resolves to nothing."
                if complete
                else f"{session.incompleteness}. Supply the imported document with "
                "--resolve to settle this."
            )
        ),
        rule=rules.EFFECTIVE_DATA_MODEL if complete else rules.CROSS_INSTANCE_SCOPE,
    )


__all__ = ["IDENTITY_TITLES", "REFERENCE_KINDS", "ReferenceKind", "check"]
