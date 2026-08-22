"""What every model-backed command starts from: the validator's own run.

A command never sees a document before the validator has. ``prepare`` runs
the deterministic validator exactly as the default command does, labels its
findings F1..Fn in the order the report prints them, and keeps the parsed
document beside them so a command can show the model an excerpt. A document
the validator cannot read raises the validator's own error, and the command
stops there: there is nothing honest to explain about a file that could not
be parsed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import __version__
from ..findings import Finding, Severity
from ..rules import OSCAL_RELEASE
from ..session import Session
from ..validator import build_session, validate
from . import PROMPT_VERSION
from .client import ModelClient
from .jsonpatch import PatchError, parent_pointer, resolve

#: A finding whose rule URL is one of these is tool policy, not a NIST rule.
POLICY_URL_PREFIX = "README.md"


@dataclass
class Run:
    document: Path
    resolve: list[Path]
    session: Session
    findings: list[Finding]
    payload: Any
    labels: dict[Finding, str] = field(default_factory=dict)

    @property
    def model(self) -> str:
        return self.session.corpus.primary.walked.model

    def label(self, finding: Finding) -> str:
        return self.labels[finding]

    def by_label(self, label: str) -> Finding | None:
        for finding, candidate in self.labels.items():
            if candidate == label:
                return finding
        return None

    @property
    def declared_version(self) -> str | None:
        for finding in self.findings:
            if finding.code == "OSCAL_VERSION_DIFFERS":
                return finding.value
        return None

    def notes_for(self, finding: Finding | None = None) -> list[str]:
        """Facts the model must carry, stated by the tool rather than left to it."""
        notes: list[str] = []
        declared = self.declared_version
        if declared is not None:
            notes.append(
                f"This document declares oscal-version {declared}. Every finding was judged "
                f"against the vendored OSCAL {OSCAL_RELEASE} schema and constraints, not "
                f"against {declared}; a rule may differ between the two (issue #8). Say so."
            )
        if finding is not None and finding.rule.url.startswith(POLICY_URL_PREFIX):
            notes.append(
                "This finding's rule is oscal-validate's own policy, not a rule NIST "
                "published. Do not attribute it to NIST."
            )
        if finding is not None and finding.severity is Severity.UNVERIFIABLE:
            notes.append(
                "This finding is UNVERIFIABLE: the validator did not decide it either way. "
                "It is not a defect and not a pass; explain what would settle it."
            )
        return notes

    def excerpt(self, location: str, limit: int = 1800) -> str:
        """The JSON around a location: the parent object, truncated and marked."""
        for pointer in (parent_pointer(location), location, ""):
            try:
                value = resolve(self.payload, pointer)
            except PatchError:
                continue
            text = json.dumps(value, indent=2, ensure_ascii=False)
            if len(text) > limit:
                text = text[:limit] + "\n... (truncated)"
            return f"at {pointer or '/'}:\n{text}"
        return "(the location could not be resolved in the document)"


def prepare(document: Path, resolve: list[Path] | None = None) -> Run:
    session = build_session(document, list(resolve or []))
    findings = validate(session)
    payload = json.loads(document.read_text(encoding="utf-8"))
    run = Run(
        document=document,
        resolve=list(resolve or []),
        session=session,
        findings=findings,
        payload=payload,
    )
    run.labels = {finding: f"F{index}" for index, finding in enumerate(findings, 1)}
    return run


def provenance(client: ModelClient, served_model: str | None = None) -> dict[str, str]:
    return {
        "tool": f"oscal-validate {__version__}",
        "provider": client.settings.provider,
        "model": served_model or client.settings.model,
        "prompt_version": PROMPT_VERSION,
    }


def banner(client: ModelClient) -> str:
    return (
        f"AI-generated text follows ({client.settings.label}, prompt {PROMPT_VERSION}). "
        "The findings are the validator's; the text is a model's reading of NIST's "
        "published documentation, with every quotation checked verbatim against it before "
        "display. Nothing below is a finding, and nothing below says whether any control is "
        "implemented or any system is secure."
    )
