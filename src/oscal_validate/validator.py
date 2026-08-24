"""Orchestration: run every check over a document and whatever came with it."""

from __future__ import annotations

from pathlib import Path

from .checks import ALL_CHECKS
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
    findings: list[Finding] = []
    for check in ALL_CHECKS:
        findings.extend(check(session))
    return finalize(_deduplicate(findings))


def validate_file(document: Path, resolve: list[Path] | None = None) -> list[Finding]:
    return validate(build_session(document, resolve))


def _deduplicate(findings: list[Finding]) -> list[Finding]:
    """One report per location and value, from the check with the strongest rule.

    NIST's constraint layer and the prose rule in check 4 overlap on a few
    identifier references. Reporting both would double-count the same defect,
    so the constraint-layer finding wins: a rule NIST states formally is a
    better citation than the same rule stated in a documentation page.
    """
    kept: list[Finding] = []
    references: dict[tuple[str, str], Finding] = {}
    for finding in findings:
        if not finding.code.startswith("REFERENCE_"):
            kept.append(finding)
            continue
        key = _reference_key(finding)
        references[key] = _prefer(references.get(key), finding)
    return kept + list(references.values())


def _reference_key(finding: Finding) -> tuple[str, str]:
    """Normalize pointer and value across constraint and prose checks.

    Constraint checks report against the containing element (e.g. ``link``)
    with a stripped fragment value, whereas prose checks report against the
    scalar (e.g. ``link/href``) with the raw leading ``#``.
    """
    location = (
        finding.location[:-5] if finding.location.endswith("/href") else finding.location
    )
    value = finding.value[1:] if finding.value.startswith("#") else finding.value
    return (location, value)


#: A constraint-layer citation names a NIST constraint id. Prefer it over the
#: same defect reported against a documentation page.
CONSTRAINT_CITATION = "NIST OSCAL constraint"


def _prefer(existing: Finding | None, candidate: Finding) -> Finding:
    if existing is None:
        return candidate
    return existing if CONSTRAINT_CITATION in existing.rule.citation else candidate
