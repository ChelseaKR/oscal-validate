"""Orchestration: run every check over a document and whatever came with it."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .checks import ALL_CHECKS, Check, constraints, references
from .corpus import build_corpus
from .findings import Finding, finalize
from .metaschema import load_metaschema
from .schema import load_schema
from .session import Session


def build_session(document: Path, resolve: list[Path] | None = None) -> Session:
    schema = load_schema()
    return Session(
        corpus=build_corpus(document, list(resolve or []), schema),
        schema=schema,
        metaschema=load_metaschema(),
    )


def validate(session: Session) -> list[Finding]:
    """Run every check. Findings come back in a deterministic order."""
    return finalize(_deduplicate((check, check(session)) for check in ALL_CHECKS))


def validate_file(document: Path, resolve: list[Path] | None = None) -> list[Finding]:
    return validate(build_session(document, resolve))


#: Two checks reach the same identifier references and both are right about
#: them, so where they collide one report is published and one is dropped.
#: This is the order they are considered in, and it is stated rather than
#: inferred from a citation string: the constraint layer names NIST's
#: constraint, the index it read, and the level NIST published, where the prose
#: check can only name a documentation page. ``_prefer`` outranks this on the
#: one question that matters more, which is whether either check was in a
#: position to answer at all.
REFERENCE_PRECEDENCE: tuple[Check, ...] = (constraints.check, references.check)

#: The code a check uses when the documents in hand could not settle the
#: question. A finding carrying it is a statement about this tool's reach.
UNSETTLED = "REFERENCE_UNVERIFIABLE"


def _deduplicate(reported: Iterable[tuple[Check, list[Finding]]]) -> list[Finding]:
    """One report per reference, from the check that was in a position to make it.

    NIST's constraint layer and the prose rule in check 4 overlap on a few
    identifier references: both reach a bare ``#`` fragment on a link, and both
    have something to say about it. Reporting both means one defect counted
    twice, under two citations, at two pointers that read like two places in
    the file. ``_reference_key`` decides which reports are about the same
    reference; ``_prefer`` decides which of them is published.
    """
    kept: list[Finding] = []
    merged: dict[tuple[str, str], tuple[int, Finding]] = {}
    for check, findings in reported:
        rank = _rank(check)
        for finding in findings:
            if not finding.code.startswith("REFERENCE_"):
                kept.append(finding)
                continue
            key = _reference_key(finding)
            merged[key] = _prefer(merged.get(key), (rank, finding))
    return kept + [finding for _, finding in merged.values()]


def _rank(check: Check) -> int:
    if check in REFERENCE_PRECEDENCE:
        return REFERENCE_PRECEDENCE.index(check)
    return len(REFERENCE_PRECEDENCE)


def _reference_key(finding: Finding) -> tuple[str, str]:
    """One key per reference, whichever check spelled it.

    Both checks describe the same href correctly and differently. The
    constraint layer reports against the node NIST's target expression
    selected, so ``link[@rel='provided-by']`` puts the pointer at
    ``.../links/0``, and its value is what NIST's own ``pattern="#(.*)"``
    captured, with the ``#`` already removed. The prose check reports against
    the scalar it read, ``.../links/0/href``, and quotes the value as written.
    Keying on the raw pair made the two spellings two keys, so the merge that
    ``_deduplicate`` exists for never fired once.

    ``prop`` separates the two exactly, with no guessing: a Metapath key-field
    source is written ``@href`` and a JSON property name is written ``href``,
    so only the prose check's own pointer is shortened here.
    """
    location = finding.location
    if finding.prop == "href" and location.endswith("/href"):
        location = location[: -len("/href")]
    return (location, finding.value.removeprefix("#"))


def _prefer(
    existing: tuple[int, Finding] | None, candidate: tuple[int, Finding]
) -> tuple[int, Finding]:
    """Which of two reports about one reference is the one to publish.

    Settledness decides first, and it outranks precedence. A settled finding
    says the reference resolves to nothing: a claim about the reader's
    document. An unsettled one says the documents in hand cannot answer: a
    claim about this tool's reach. When the two land on the same value only
    one of them can be true of this run, and it is the second. A check that
    has just reported it could not perform the lookup does not become able to
    perform it because another check, looking somewhere else, came back empty.

    The case is neither hypothetical nor symmetric. The only way a constraint
    finding is unsettled while a prose finding is settled is an
    ``index-has-key`` reading an index that was never built, and OSCAL 1.2.3
    publishes exactly one: ``oscal-by-component-uuid-index``, on
    ``link[@rel='provided-by']``. NIST declares that index over this
    document's own ``//by-component`` *and* over the by-components of a second
    document, reached with ``doc()`` from
    ``system-implementation/leveraged-authorization/link[@rel=...]/@href``.
    A leveraged authorization's SSP arrives through a link, not through an
    import, so it is not a document ``--resolve`` completeness ever accounts
    for. "Every import was supplied" is therefore not a stronger answer about
    a ``provided-by`` href; it answers a smaller question, and the target may
    sit in a document this tool was never given and could not have opened.
    Publishing the ERROR would report a defect in someone's file on the
    strength of a lookup this tool had already said it did not make, which is
    what ADR-0002 forbids and what docs/CONSTRAINT-COVERAGE.md already tells
    readers does not happen. ADR-0006 records the decision.

    Severity ordering would reach the right answer here for the wrong reason
    and the wrong answer elsewhere: NIST's published ``level`` is carried into
    the severity, so a settled constraint failure can be a WARNING, and an
    order that ranked by severity would drop it for a prose ERROR and silently
    raise NIST's own level. Where both reports agree on settledness,
    ``REFERENCE_PRECEDENCE`` decides, and ties keep the report already held.
    """
    if existing is None:
        return candidate
    unsettled = [report for report in (existing, candidate) if report[1].code == UNSETTLED]
    if len(unsettled) == 1:
        return unsettled[0]
    return existing if existing[0] <= candidate[0] else candidate
