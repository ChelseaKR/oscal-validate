"""Check 3: NIST's own constraint layer, run against the document.

Everything here comes from the vendored ``*_metaschema_RESOLVED.xml`` files.
This module contributes the machinery to evaluate a constraint; it contributes
no constraints of its own, and it cannot: a rule that is not in those files
cannot be expressed through this path.

Severity is NIST's. A constraint declared at ``level="WARNING"`` produces a
WARNING here even where a stricter reading would call it an error, because the
published level is part of the published rule.

An ``index-has-key`` failure is reported as an ERROR only when every document
the primary imports was supplied. OSCAL identifiers are cross-instance scoped,
so a key that is absent from the documents in hand may be present in one that
was not; that case is UNVERIFIABLE and says which documents were missing.

It is also reported as an ERROR only when the index it looks in was actually
built. Some indexes are declared by an ``index`` constraint whose target
expression is outside the Metapath subset this tool parses, and a lookup into
an index that was never built misses everything. Reporting that as a failure of
the document would be the mirror image of the mistake this tool exists to
avoid: it would turn a rule that was not evaluated into a finding against
someone's file. Those references are UNVERIFIABLE, and they name the index.
"""

from __future__ import annotations

import itertools
from collections import defaultdict

from .. import rules
from ..findings import Finding, Rule, Severity
from ..metaschema import (
    UNEVALUATED_KINDS,
    Constraint,
    Located,
    Metaschema,
    Step,
    key_values,
    select,
    select_paths,
)
from ..session import Session

#: NIST's constraint levels, mapped onto this tool's severities.
LEVELS = {
    "CRITICAL": Severity.ERROR,
    "ERROR": Severity.ERROR,
    "WARNING": Severity.WARNING,
    "INFORMATIONAL": Severity.INFO,
    "DEBUG": Severity.INFO,
}

Key = tuple[str | None, ...]

#: A stated interpretation, not a rule read out of a file. The Metaschema
#: specification says that where a key-field selects nothing, "its value for
#: that key in the index is null", which read literally would make every object
#: missing the whole key collide with every other. NIST's own published catalogs
#: contain many props with no ``uuid`` and are not treated as invalid, so an
#: entry whose composite key is null in every part is left out of the index and
#: out of the uniqueness comparison rather than reported. Where a key has some
#: parts present and some absent, the absent parts are nulls and the entry is
#: compared, which is what makes the multi-part metadata keys work.
NULL_KEY_INTERPRETATION = "https://pages.nist.gov/metaschema/specification/syntax/constraints/"


def constraint_rule(constraint: Constraint, detail: str = "") -> Rule:
    return Rule(
        citation=(
            f"NIST OSCAL constraint {constraint.identifier} ({constraint.kind}, "
            f"level {constraint.level}), declared on {constraint.context} in "
            f"{constraint.module} at OSCAL {rules.OSCAL_RELEASE}: target "
            f"{constraint.target!r}, key "
            f"{', '.join(k.source for k in constraint.key_fields) or '(none)'}. "
            f"{detail}".strip()
        ),
        url=(
            "https://github.com/usnistgov/OSCAL/releases/download/"
            f"v{rules.OSCAL_RELEASE}/{constraint.module}"
        ),
        retrieved=rules.RETRIEVED,
    )


def keys_for(node: object, constraint: Constraint, metaschema: Metaschema) -> list[Key]:
    """The composite key(s) a constraint computes for one node.

    Per the Metaschema specification, a key-field that selects nothing
    contributes a null to the key rather than removing the entry.
    """
    per_field: list[list[str | None]] = []
    for field in constraint.key_fields:
        values = key_values(node, field, metaschema)
        per_field.append([*values] if values else [None])
    return [tuple(combination) for combination in itertools.product(*per_field)]


def _contexts(
    payload: dict[str, object], constraint: Constraint, metaschema: Metaschema
) -> list[Located]:
    """Every node a constraint's declaring assembly appears at in a document."""
    step = Step(names=(constraint.context,), descendant=True)
    return select(payload, "", (step,), metaschema)


def _index_key(name: str, key: Key) -> tuple[str, Key]:
    return (name, key)


def build_indexes(session: Session) -> dict[tuple[str, Key], str]:
    """Every named index NIST declares, built across all supplied documents."""
    built: dict[tuple[str, Key], str] = {}
    for document in session.corpus.reachable:
        payload = {document.walked.model: document.walked.root}
        for constraint in session.metaschema.evaluated(document.walked.model):
            if constraint.kind != "index" or constraint.paths is None:
                continue
            for context in _contexts(payload, constraint, session.metaschema):
                for located in select_paths(
                    context.value, context.pointer, constraint.paths, session.metaschema
                ):
                    for key in keys_for(located.value, constraint, session.metaschema):
                        if all(part is None for part in key):
                            continue  # see NULL_KEY_INTERPRETATION
                        built.setdefault(
                            _index_key(constraint.index_name, key),
                            f"{document.name}{located.pointer}",
                        )
    return built


def buildable_indexes(session: Session) -> frozenset[str]:
    """Index names that some evaluated ``index`` constraint actually builds.

    An ``index-has-key`` naming anything outside this set has nothing to look
    its key up in, because the constraint that would have populated the index
    was skipped. See this module's docstring for why that is UNVERIFIABLE and
    not a finding against the document.
    """
    return frozenset(
        constraint.index_name
        for document in session.corpus.reachable
        for constraint in session.metaschema.evaluated(document.walked.model)
        if constraint.kind == "index"
    )


def check(session: Session) -> list[Finding]:
    findings: list[Finding] = []
    indexes = build_indexes(session)
    buildable = buildable_indexes(session)
    walked = session.corpus.primary.walked
    payload: dict[str, object] = {walked.model: walked.root}
    for constraint in session.metaschema.evaluated(walked.model):
        if constraint.paths is None:  # pragma: no cover - evaluated implies parsed
            continue
        for context in _contexts(payload, constraint, session.metaschema):
            selected = select_paths(
                context.value, context.pointer, constraint.paths, session.metaschema
            )
            if constraint.kind in ("is-unique", "index"):
                findings.extend(_uniqueness(constraint, selected, session))
            elif constraint.kind == "index-has-key":
                findings.extend(_cross_reference(constraint, selected, indexes, buildable, session))
            elif constraint.kind == "has-cardinality":
                findings.extend(_cardinality(constraint, context, selected))
    findings.extend(_coverage(session))
    return findings


def _uniqueness(constraint: Constraint, selected: list[Located], session: Session) -> list[Finding]:
    seen: dict[Key, str] = {}
    findings: list[Finding] = []
    for located in selected:
        for key in keys_for(located.value, constraint, session.metaschema):
            if all(part is None for part in key):
                continue  # see NULL_KEY_INTERPRETATION
            first = seen.setdefault(key, located.pointer)
            if first == located.pointer:
                continue
            findings.append(
                Finding(
                    code="CONSTRAINT_NOT_UNIQUE",
                    severity=LEVELS.get(constraint.level, Severity.ERROR),
                    location=located.pointer,
                    prop=", ".join(field.source for field in constraint.key_fields),
                    value=_render(key),
                    message=(
                        f"This key is already used at {first}. NIST's constraint "
                        f"{constraint.identifier} requires it to be unique among the "
                        f"{constraint.target!r} of each {constraint.context}."
                    ),
                    rule=constraint_rule(
                        constraint,
                        "An index constraint requires each member entry to be unique on "
                        "its composite key.",
                    ),
                )
            )
    return findings


def _unsettled(constraint: Constraint, built: bool, incompleteness: str) -> str:
    """Why an ``index-has-key`` could not be settled, when it could not be."""
    if not built:
        return (
            f"NIST declares the {constraint.index_name!r} index on a target expression outside "
            "the Metapath subset this tool parses, so the index was never built and this key "
            "could not be looked up in it. The reference is neither resolved nor unresolved "
            "here; see docs/CONSTRAINT-COVERAGE.md."
        )
    return f"{incompleteness}, so whether this resolves cannot be settled here."


def _unsettled_rule(built: bool) -> Rule:
    """The authority for a report that the question was not settled.

    The two reasons an ``index-has-key`` goes unsettled are different rules,
    and citing one of them for the other sends the reader to do something that
    cannot help. An index that was never built is this tool's own limit: no
    document supplied with ``--resolve`` populates it. A document that was not
    supplied is what NIST's cross-instance scope paragraph is about, and
    supplying it settles the question. ``_unsettled`` picks the message on the
    same fact, so the citation and the message cannot come apart.
    """
    return rules.CROSS_INSTANCE_SCOPE if built else rules.INDEX_NEVER_BUILT


def _cross_reference(
    constraint: Constraint,
    selected: list[Located],
    indexes: dict[tuple[str, Key], str],
    buildable: frozenset[str],
    session: Session,
) -> list[Finding]:
    findings: list[Finding] = []
    built = constraint.index_name in buildable
    settled = session.complete and built
    for located in selected:
        for key in keys_for(located.value, constraint, session.metaschema):
            if all(part is None for part in key):
                continue
            if _index_key(constraint.index_name, key) in indexes:
                continue
            findings.append(
                Finding(
                    code="REFERENCE_UNRESOLVED" if settled else "REFERENCE_UNVERIFIABLE",
                    severity=LEVELS.get(constraint.level, Severity.ERROR)
                    if settled
                    else Severity.UNVERIFIABLE,
                    location=located.pointer,
                    prop=", ".join(field.source for field in constraint.key_fields),
                    value=_render(key),
                    message=(
                        f"Nothing in the {constraint.index_name!r} index carries this key. "
                        + (
                            "Every document this reference could reach was supplied, so it "
                            "resolves to nothing."
                            if settled
                            else _unsettled(constraint, built, session.incompleteness)
                        )
                    ),
                    rule=constraint_rule(constraint) if settled else _unsettled_rule(built),
                )
            )
    return findings


def _cardinality(
    constraint: Constraint, context: Located, selected: list[Located]
) -> list[Finding]:
    count = len(selected)
    low = constraint.min_occurs
    high = constraint.max_occurs
    if (low is None or count >= low) and (high is None or count <= high):
        return []
    bounds = []
    if low is not None:
        bounds.append(f"at least {low}")
    if high is not None:
        bounds.append(f"at most {high}")
    return [
        Finding(
            code="CONSTRAINT_CARDINALITY",
            severity=LEVELS.get(constraint.level, Severity.ERROR),
            location=context.pointer,
            prop=constraint.target,
            value=f"{count} present",
            message=(
                f"NIST's constraint {constraint.identifier} requires "
                f"{' and '.join(bounds)} {constraint.target!r} here."
            ),
            rule=constraint_rule(constraint),
        )
    ]


def _coverage(session: Session) -> list[Finding]:
    """One finding per constraint kind this tool did not evaluate.

    Reported so that "no findings" can never be read as "every published
    constraint passed". It is not the same claim and it is not merged with it.
    """
    by_kind: defaultdict[str, list[str]] = defaultdict(list)
    for constraint in session.metaschema.skipped():
        by_kind[constraint.kind].append(constraint.identifier or constraint.target)
    model = session.corpus.primary.walked.model
    reasons = {
        kind: UNEVALUATED_KINDS.get(
            kind,
            "their target expressions are outside the Metapath subset this tool parses",
        )
        for kind in by_kind
    }
    return [
        Finding(
            code="CONSTRAINT_NOT_EVALUATED",
            severity=Severity.UNVERIFIABLE,
            location=f"/{model}",
            prop=kind,
            value=f"{len(identifiers)} constraint(s)",
            message=(
                f"NIST publishes {len(identifiers)} {kind} constraint(s) that this tool "
                f"did not evaluate: {reasons[kind]}. They are neither passed nor failed. "
                "Every one of them is listed, with its reason, in "
                "docs/CONSTRAINT-COVERAGE.md."
            ),
            rule=rules.NOT_WALKED_POLICY,
        )
        for kind, identifiers in sorted(by_kind.items())
    ]


def _render(key: Key) -> str:
    return " | ".join("(absent)" if part is None else part for part in key)
