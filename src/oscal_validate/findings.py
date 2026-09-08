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
from dataclasses import dataclass, field
from enum import StrEnum

from .report import REPORT_SCHEMA_VERSION
from .suggest import Suggestion


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
class Acknowledgement:
    """Why a finding was accepted, and when. Never why it stopped being true.

    A baseline entry carries one. It changes exactly one thing: whether the
    finding gates the exit code. It does not change the severity, does not
    remove the finding from the report, and does not remove it from the
    counts, because a document with three acknowledged ERRORs has three
    ERRORs in it and saying otherwise is the failure this tool exists to
    prevent.
    """

    reason: str
    acknowledged_on: str

    def to_dict(self) -> dict[str, str]:
        return {"reason": self.reason, "acknowledged_on": self.acknowledged_on}

    def render_text(self) -> str:
        return (
            f"    ACKNOWLEDGED {self.acknowledged_on}: {self.reason}\n"
            "    Still an ERROR and still counted; acknowledged findings do not "
            "gate the exit code."
        )


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
    #: Identifiers close to :attr:`value` that *are* declared, offered only
    #: when ``--suggest`` is on and only for a settled finding (issue #64).
    #: Empty by default, and absent from both renderings when empty, so the
    #: bytes of a run without the flag are the bytes this tool always emitted.
    suggestions: tuple[Suggestion, ...] = field(default=())
    #: Set only when ``--baseline`` matched this finding (issue #63). Absent
    #: by default, and absent from both renderings when absent, so a run
    #: without the flag emits the bytes this tool always emitted.
    acknowledged: Acknowledgement | None = field(default=None)

    @property
    def gates(self) -> bool:
        """Whether this finding makes the command exit nonzero.

        The one place the answer is written down. An ERROR gates unless a
        baseline entry acknowledged it; nothing else ever gates, and an
        acknowledged finding is still an ERROR everywhere else it appears.
        """
        return self.severity is Severity.ERROR and self.acknowledged is None

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
        payload: dict[str, object] = {
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
        if self.suggestions:
            payload["suggestions"] = [s.to_dict() for s in self.suggestions]
        if self.acknowledged is not None:
            payload["acknowledged"] = self.acknowledged.to_dict()
        return payload

    def render_text(self) -> str:
        acknowledged = "" if self.acknowledged is None else "\n" + self.acknowledged.render_text()
        return (
            f"{self.severity.value:12} {self.code}  at={self.location}\n"
            f"    {self.prop} = {self.value}\n"
            f"    {self.message}\n"
            f"    rule: {self.rule.citation}\n"
            f"    source: {self.rule.url} (retrieved {self.rule.retrieved})"
            + acknowledged
            + "".join("\n" + s.render_text() for s in self.suggestions)
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


#: The code a stale baseline entry is reported under. It lives here rather than
#: in :mod:`oscal_validate.baseline` because both the renderers and the counts
#: need it and neither may import that module.
BASELINE_STALE = "BASELINE_STALE"


def acknowledged_count(findings: list[Finding]) -> int:
    return sum(1 for f in findings if f.acknowledged is not None)


def stale_count(findings: list[Finding]) -> int:
    return sum(1 for f in findings if f.code == BASELINE_STALE)


def _baseline_block(findings: list[Finding], path: str) -> dict[str, object]:
    """What a baseline did to this run, derived rather than restated.

    Both numbers are counted off the findings the report carries, so a report
    cannot claim an acknowledgement it does not show.
    """
    return {
        "path": path,
        "acknowledged": acknowledged_count(findings),
        "stale": stale_count(findings),
    }


def render_findings_json(
    findings: list[Finding], version: str, model: str, baseline: str = ""
) -> str:
    """The canonical machine-readable report.

    ``report_schema_version`` names the published shape this conforms to, so a
    consumer can check what it is reading instead of inferring it from the
    tool version. See :mod:`oscal_validate.report`.

    ``baseline`` is the path a ``--baseline`` file was read from, or ``""``
    when none was. Empty means the key is absent, and absent is not the same
    as a baseline that acknowledged nothing: a run that was never given one
    makes no claim either way.
    """
    payload: dict[str, object] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "tool": {"name": "oscal-validate", "version": version},
        "document": {"model": model},
        "findings": [f.to_dict() for f in findings],
        "summary": counts(findings),
    }
    if baseline:
        payload["baseline"] = _baseline_block(findings, baseline)
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def render_findings_text(findings: list[Finding], model: str, baseline: str = "") -> str:
    lines = [f"model: {model}\n"]
    lines.extend(f.render_text() + "\n" for f in findings)
    summary = ", ".join(f"{counts(findings)[s.value]} {s.value}" for s in SEVERITY_ORDER)
    lines.append(f"{len(findings)} finding(s): {summary}")
    if baseline:
        lines.append(
            f"baseline {baseline}: {acknowledged_count(findings)} finding(s) acknowledged "
            f"and not gating, {stale_count(findings)} entry(ies) stale. Acknowledged "
            "findings are still counted above."
        )
    return "\n".join(lines)
