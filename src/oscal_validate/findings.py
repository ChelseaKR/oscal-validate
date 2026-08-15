"""Finding model: severities, rule citations, deterministic ordering.

The severity semantics here are the contract of the whole tool:

- ERROR: the document violates a cited structural rule.
- WARNING: a cited signal that something is very likely wrong, where the rule
  is not absolute or its enforcement by any authorizing body is not documented.
- INFO: worth a human look; not a defect on its own.
- UNVERIFIABLE: the answer cannot be determined from the documents supplied and
  the tool refuses to guess. Never counted as a pass or a fail.

Only ERROR findings make the CLI exit nonzero.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class Rule:
    """Where a rule comes from. Every finding carries one.

    ``retrieved`` is the date the cited source was downloaded, or ``"-"`` when
    the citation is tool policy rather than an external document.
    """

    citation: str
    url: str
    retrieved: str


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    #: RFC 6901 JSON Pointer to the location in the document.
    location: str
    prop: str
    value: str
    message: str
    rule: Rule

    def sort_key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.location,
            self.prop,
            self.code,
            self.value,
            self.severity.value,
            self.message,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "location": self.location,
            "property": self.prop,
            "value": self.value,
            "message": self.message,
            "rule": {
                "citation": self.rule.citation,
                "url": self.rule.url,
                "retrieved": self.rule.retrieved,
            },
        }

    def render_text(self) -> str:
        return (
            f"{self.severity.value:12} {self.code}  at={self.location}\n"
            f"    {self.prop} = {self.value}\n"
            f"    {self.message}\n"
            f"    rule: {self.rule.citation}\n"
            f"    source: {self.rule.url} (retrieved {self.rule.retrieved})"
        )


def finalize(findings: list[Finding]) -> list[Finding]:
    """Deduplicate and order findings deterministically."""
    return sorted(set(findings), key=Finding.sort_key)


#: The order severities are counted and printed in, everywhere.
SEVERITY_ORDER = (Severity.ERROR, Severity.WARNING, Severity.INFO, Severity.UNVERIFIABLE)


def counts(findings: list[Finding]) -> dict[str, int]:
    return {
        severity.value: sum(1 for f in findings if f.severity is severity)
        for severity in SEVERITY_ORDER
    }


def render_findings_json(findings: list[Finding], version: str, model: str) -> str:
    payload = {
        "tool": {"name": "oscal-validate", "version": version},
        "document": {"model": model},
        "findings": [f.to_dict() for f in findings],
        "summary": counts(findings),
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def render_findings_text(findings: list[Finding], model: str) -> str:
    lines = [f"model: {model}\n"]
    lines.extend(f.render_text() + "\n" for f in findings)
    summary = ", ".join(f"{counts(findings)[s.value]} {s.value}" for s in SEVERITY_ORDER)
    lines.append(f"{len(findings)} finding(s): {summary}")
    return "\n".join(lines)
