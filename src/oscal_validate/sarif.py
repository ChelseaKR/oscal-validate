"""SARIF 2.1.0 output: the same findings, in the format code-scanning viewers read.

The JSON report (``--format json``) is the canonical machine-readable form.
This module renders the same findings into SARIF without adding to them,
dropping any, or merging any. Three rules of the rendering are worth
stating, because each one is a place where a format conversion could quietly
turn "not checked" into "passed".

**Severity to result ``kind`` and ``level``.** SARIF separates what a result
*is* (``kind``) from how loudly to show it (``level``). The tool's four
severities map onto both:

===============  ===============  =========
severity         kind             level
===============  ===============  =========
ERROR            ``fail``         ``error``
WARNING          ``fail``         ``warning``
INFO             ``informational``  ``note``
UNVERIFIABLE     ``open``         ``note``
===============  ===============  =========

``open`` is SARIF's own word for "the rule was evaluated and the result could
not be settled", which is exactly what UNVERIFIABLE means here. No result is
ever rendered with ``kind: pass``. The tool reports findings and only
findings; an empty ``results`` array would mean the validator produced none,
and it never does, because a run always lists the constraints it did not
evaluate.

One deliberate departure from the specification's prose: SARIF 2.1.0
section 3.27.10 says a result whose ``kind`` is not ``fail`` should carry
``level: none``. GitHub code scanning ignores ``kind`` and decides what to
display from ``level`` alone, and documents ``note``, ``warning``, and
``error`` as the levels it renders. A ``level: none`` UNVERIFIABLE finding
would therefore vanish from the one place this format is most often read,
which is the absence-as-pass this tool exists to refuse. So non-``fail``
results carry ``level: note``. The JSON schema accepts it; a viewer that
honours ``kind`` sees the distinction; a viewer that does not still shows the
finding. The tool's own severity is carried verbatim in every result's
``properties.severity`` for anything that wants it.

**Rules.** Every finding code becomes one ``reportingDescriptor`` in
``tool.driver.rules``, with ``id`` equal to the code. A code is not always
one citation, though: ``REFERENCE_UNRESOLVED`` cites NIST's constraint layer
when a constraint settled it and the URI-usage prose when the reference check
did, and a schema-shape code cites the schema with the assembly and property
spelled out per finding. The per-finding citation, URL, and retrieval date
therefore travel on each result, in ``properties.rule``, exactly as the JSON
report carries them. The rule descriptor carries ``helpUri`` when every
finding under that code in this report cites one URL, and lists every source
with its retrieval date under ``properties.sources`` regardless.

**Locations.** A finding's location is an RFC 6901 JSON Pointer, or
``<path>#<pointer>`` when it is in a supporting document passed through
``--resolve``. SARIF gets the document as a ``physicalLocation`` (GitHub
needs one to display anything) and the pointer as a ``logicalLocation``. No
line or column is reported, because the validator does not track one, and a
region would be an invented number.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .findings import Finding, Severity, counts

#: Where the tool is described. SARIF's ``informationUri`` for the driver.
INFORMATION_URI = "https://github.com/ChelseaKR/oscal-validate"

#: The schema this file claims conformance with; a viewer can check it.
SCHEMA_URI = "https://json.schemastore.org/sarif-2.1.0.json"

#: Severity to SARIF ``(kind, level)``. See the module docstring.
KINDS: dict[Severity, tuple[str, str]] = {
    Severity.ERROR: ("fail", "error"),
    Severity.WARNING: ("fail", "warning"),
    Severity.INFO: ("informational", "note"),
    Severity.UNVERIFIABLE: ("open", "note"),
}

#: The name under which a result's stable identity is published. GitHub
#: uses ``partialFingerprints`` to match an alert across uploads; without
#: one it hashes the source line, and there is no line here.
FINGERPRINT = "oscalValidate/finding/v1"

#: One line per finding code, describing what the code reports. These
#: describe this tool's own output; the rule each finding cites is NIST's and
#: travels on the finding itself.
DESCRIPTIONS: dict[str, str] = {
    "IMPORT_RESOLVED": "An import named by the document matched a supplied file.",
    "IMPORT_NOT_SUPPLIED": "An import named by the document matched no supplied file.",
    "IMPORT_AMBIGUOUS": "An import named by the document matched more than one supplied file.",
    "REQUIRED_PROPERTY_MISSING": "A property the schema requires is absent.",
    "PROPERTY_UNDECLARED": "A property is present that the schema does not declare.",
    "TYPE_MISMATCH": "A value is of a different JSON type than the schema declares.",
    "ARRAY_TOO_SHORT": "An array is present with fewer items than the schema's minimum.",
    "NO_SCHEMA_ALTERNATIVE": "An object satisfies none of the alternatives the schema declares.",
    "SUBTREE_NOT_READ": (
        "A subtree was left unread because the schema combines alternatives in a form "
        "this tool does not resolve."
    ),
    "DATATYPE_MISMATCH": "A scalar value does not match the pattern its datatype declares.",
    "DATATYPE_BELOW_MINIMUM": "A numeric value is below the minimum its datatype declares.",
    "PATTERN_NOT_CHECKED": (
        "Values governed by a pattern this tool cannot compile were neither passed nor failed."
    ),
    "CONSTRAINT_NOT_UNIQUE": "A value that a NIST constraint requires to be unique is repeated.",
    "CONSTRAINT_CARDINALITY": "A NIST cardinality constraint is not met.",
    "CONSTRAINT_VALUE_MISMATCH": (
        "A value does not match the syntax a NIST matches constraint declares for it."
    ),
    "CONSTRAINT_NOT_EVALUATED": "A NIST constraint in scope for this document was not evaluated.",
    "REFERENCE_UNRESOLVED": (
        "A reference names an identifier that the complete effective data model does not declare."
    ),
    "REFERENCE_UNVERIFIABLE": (
        "A reference could not be settled because the effective data model is incomplete."
    ),
    "UUID_NOT_UNIQUE": "Two objects in one document carry the same UUID.",
    "OSCAL_VERSION_DIFFERS": (
        "The document declares an OSCAL release other than the one it was judged against."
    ),
}


def _split_location(location: str, model: str) -> tuple[str | None, str]:
    """``(path, pointer)`` from a finding location; the path is None for the primary.

    A pointer into the primary document always begins with the model root, so
    a location that does is a pointer whatever else it contains; anything
    else of the form ``<path>#<pointer>`` is a supporting document.
    """
    if location == f"/{model}" or location.startswith(f"/{model}/"):
        return None, location
    path, separator, pointer = location.partition("#")
    if not separator or not path or not pointer.startswith("/"):
        return None, location
    return path, pointer


def _artifact_uri(path: Path) -> str:
    """A relative path as given, or a ``file:`` URI for an absolute one."""
    return path.as_uri() if path.is_absolute() else path.as_posix()


def _logical_location(pointer: str) -> dict[str, str]:
    segments = [s for s in pointer.split("/") if s]
    name = segments[-1] if segments else pointer
    return {"name": name, "fullyQualifiedName": pointer}


def _fingerprint(finding: Finding) -> str:
    identity = "\x1f".join(
        (finding.code, finding.location, finding.prop, finding.rule.url, finding.rule.citation)
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _message(finding: Finding) -> str:
    return (
        f"{finding.prop} = {finding.value} at {finding.location}. {finding.message}\n\n"
        f"Rule: {finding.rule.citation}\n"
        f"Source: {finding.rule.url} (retrieved {finding.rule.retrieved})"
    )


def _result(finding: Finding, rule_index: int, document: Path, model: str) -> dict[str, Any]:
    kind, level = KINDS[finding.severity]
    path, pointer = _split_location(finding.location, model)
    artifact = Path(path) if path is not None else document
    return {
        "ruleId": finding.code,
        "ruleIndex": rule_index,
        "kind": kind,
        "level": level,
        "message": {"text": _message(finding)},
        "locations": [
            {
                "physicalLocation": {"artifactLocation": {"uri": _artifact_uri(artifact)}},
                "logicalLocations": [_logical_location(pointer)],
            }
        ],
        "partialFingerprints": {FINGERPRINT: _fingerprint(finding)},
        "properties": {
            "severity": finding.severity.value,
            "location": finding.location,
            "property": finding.prop,
            "value": finding.value,
            "rule": {
                "citation": finding.rule.citation,
                "url": finding.rule.url,
                "retrieved": finding.rule.retrieved,
            },
        },
    }


def _rules(findings: list[Finding]) -> list[dict[str, Any]]:
    sources: dict[str, set[tuple[str, str]]] = {}
    for finding in findings:
        sources.setdefault(finding.code, set()).add((finding.rule.url, finding.rule.retrieved))
    rules: list[dict[str, Any]] = []
    for code in sorted(sources):
        cited = sorted(sources[code])
        rule: dict[str, Any] = {"id": code, "name": code}
        description = DESCRIPTIONS.get(code)
        if description is not None:
            rule["shortDescription"] = {"text": description}
        urls = {url for url, _ in cited}
        if len(urls) == 1 and next(iter(urls)).startswith(("http://", "https://")):
            rule["helpUri"] = next(iter(urls))
        rule["properties"] = {
            "sources": [{"url": url, "retrieved": retrieved} for url, retrieved in cited]
        }
        rules.append(rule)
    return rules


def render_findings_sarif(findings: list[Finding], version: str, model: str, document: Path) -> str:
    """The SARIF 2.1.0 log for one validation run, as deterministic JSON."""
    rules = _rules(findings)
    index = {rule["id"]: position for position, rule in enumerate(rules)}
    log = {
        "$schema": SCHEMA_URI,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "oscal-validate",
                        "version": version,
                        "semanticVersion": version,
                        "informationUri": INFORMATION_URI,
                        "rules": rules,
                    }
                },
                "results": [_result(f, index[f.code], document, model) for f in findings],
                "properties": {
                    "document": {"model": model},
                    "summary": counts(findings),
                },
            }
        ],
    }
    return json.dumps(log, indent=2, sort_keys=True, ensure_ascii=False)
