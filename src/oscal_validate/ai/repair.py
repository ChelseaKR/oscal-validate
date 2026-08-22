"""``repair --draft``: a proposed edit, re-validated before it is shown, never applied.

For one finding the model proposes a JSON Patch. The patch is applied to an
in-memory copy of the document, the copy is written to a temporary
directory under the document's own file name (so import matching by name
still works) and run through the deterministic validator with the same
``--resolve`` documents. What that run found is the report: whether the
target finding is gone, which other findings went with it, which findings
changed, and which findings are new. The model claims nothing about the
effect of its patch; the validator says what the effect was.

The original file is never written. ``--out`` writes the patched copy to a
path that is not the original, and only that.

Two refusals sit in front of the validator. A patch that cannot be applied
as written (a path that does not exist, an operation outside add, remove,
replace) is reported and not shown as a draft. And a patch whose values
carry a sentence the boundary guard would withhold -- an implementation
narrative written into a description, say -- is refused whole: an edit that
asserts a control is implemented is exactly the edit this tool must never
draft.
"""

from __future__ import annotations

import difflib
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..findings import Finding, counts
from ..validator import validate_file
from . import guard, prompts, sources
from .client import ModelClient, ModelError
from .jsonpatch import Operation, PatchError, apply
from .run import Run, provenance
from .verify import ReplyError, Verified, parse_reply, render_quotes, render_withheld, verify

#: Words in a patch value that mark it as something the author must replace.
PLACEHOLDER_MARKS = ("TODO", "PLACEHOLDER", "REPLACE", "FIXME", "CHANGEME")


def finding_key(finding: Finding) -> tuple[str, str, str, str]:
    """What makes a finding the same finding before and after a patch.

    Code, location, and property, plus the rule citation: two constraints
    can fail at one location on one property (the catalog's two id indexes
    do), and the citation is what tells them apart. Value and message are
    left out so that a finding whose count or value moved is reported as
    changed rather than as one resolved and one introduced.
    """
    return (finding.code, finding.location, finding.prop, finding.rule.citation)


@dataclass
class Outcome:
    """What the validator found after the patch, relative to before."""

    resolved: bool
    also_resolved: list[Finding]
    changed: list[tuple[Finding, Finding]]
    introduced: list[Finding]
    unchanged: int
    before: dict[str, int]
    after: dict[str, int]
    diff: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved": self.resolved,
            "also_resolved": [f.to_dict() for f in self.also_resolved],
            "changed": [{"before": b.to_dict(), "after": a.to_dict()} for b, a in self.changed],
            "introduced": [f.to_dict() for f in self.introduced],
            "unchanged": self.unchanged,
            "before": self.before,
            "after": self.after,
            "diff": self.diff,
        }


@dataclass
class Repair:
    label: str
    finding: Finding
    verified: Verified | None = None
    patch: list[Operation] = field(default_factory=list)
    placeholders: list[dict[str, str]] = field(default_factory=list)
    outcome: Outcome | None = None
    patched: Any = None
    skipped: str = ""
    served_model: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"label": self.label, "finding": self.finding.to_dict()}
        if self.skipped:
            out["skipped"] = self.skipped
        if self.verified is not None:
            v = self.verified
            out.update(
                {
                    "refused": v.refused,
                    "refusal": v.refusal,
                    "rationale": v.prose,
                    "quotes": [
                        {"id": q.identifier, "source": q.source, "text": q.text, "url": q.url}
                        for q in v.quotes
                    ],
                    "withheld_quotes": len(v.withheld_quotes),
                    "withheld_sentences": len(v.withheld_sentences),
                }
            )
        out["patch"] = [op.to_dict() for op in self.patch]
        out["placeholders"] = self.placeholders
        out["outcome"] = self.outcome.to_dict() if self.outcome else None
        return out


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _placeholders(raw: Any, patch: list[Operation]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("path"):
                out.append({"path": str(item["path"]), "why": str(item.get("why", ""))})
    declared = {p["path"] for p in out}
    for op in patch:
        marked = any(mark in s.upper() for s in _strings(op.value) for mark in PLACEHOLDER_MARKS)
        if marked and op.path not in declared:
            out.append({"path": op.path, "why": "the value is marked as a placeholder"})
    return out


def revalidate(run: Run, patched: Any) -> Outcome:
    """Write the patched copy to a temporary directory and validate it for real."""
    before = {finding_key(f): f for f in run.findings}
    with tempfile.TemporaryDirectory() as directory:
        copy_path = Path(directory) / run.document.name
        copy_path.write_text(json.dumps(patched, indent=2, ensure_ascii=False), encoding="utf-8")
        after_findings = validate_file(copy_path, run.resolve)
    after = {finding_key(f): f for f in after_findings}
    resolved_keys = [k for k in before if k not in after]
    introduced = [after[k] for k in after if k not in before]
    changed = [(before[k], after[k]) for k in before if k in after and before[k] != after[k]]
    unchanged = sum(1 for k in before if k in after and before[k] == after[k])
    original = json.dumps(run.payload, indent=2, ensure_ascii=False).splitlines()
    revised = json.dumps(patched, indent=2, ensure_ascii=False).splitlines()
    diff = "\n".join(
        difflib.unified_diff(
            original, revised, f"a/{run.document.name}", f"b/{run.document.name}", lineterm="", n=3
        )
    )
    return Outcome(
        resolved=False,
        also_resolved=[before[k] for k in resolved_keys],
        changed=changed,
        introduced=introduced,
        unchanged=unchanged,
        before=counts(run.findings),
        after=counts(after_findings),
        diff=diff,
    )


def _settle_target(outcome: Outcome, finding: Finding) -> None:
    key = finding_key(finding)
    hits = [f for f in outcome.also_resolved if finding_key(f) == key]
    if hits:
        outcome.resolved = True
        outcome.also_resolved = [f for f in outcome.also_resolved if finding_key(f) != key]


def repair_one(run: Run, finding: Finding, client: ModelClient) -> Repair:
    label = run.label(finding)
    repair = Repair(label=label, finding=finding)
    passages = sources.passages_for_finding(finding, run.model)
    user = prompts.repair_user(
        finding.to_dict(),
        run.model,
        run.excerpt(finding.location),
        passages,
        run.notes_for(finding),
    )
    try:
        completion = client.complete(prompts.SYSTEM, user)
    except ModelError as exc:
        repair.skipped = f"the model call failed: {exc}"
        return repair
    try:
        payload = parse_reply(completion.text)
    except ReplyError as exc:
        repair.skipped = f"the model's reply was unusable ({exc}); nothing shown"
        return repair
    repair.served_model = completion.model
    repair.verified = verify(payload, "rationale")
    try:
        raw_patch = payload.get("patch") or []
        if not isinstance(raw_patch, list):
            raise PatchError("patch is not a list")
        repair.patch = [Operation.from_dict(op) for op in raw_patch if isinstance(op, dict)]
    except PatchError as exc:
        repair.skipped = f"the proposed patch is not usable: {exc}"
        return repair
    if not repair.patch:
        repair.skipped = "the model proposed no patch; see its rationale"
        return repair
    screened = guard.screen_values([s for op in repair.patch for s in _strings(op.value)])
    if screened.withheld:
        repair.skipped = (
            f"the proposed patch carried {screened.withheld_count} sentence(s) the boundary guard "
            "withholds (implementation, security, or authorization narrative); no draft shown"
        )
        repair.patch = []
        return repair
    repair.placeholders = _placeholders(payload.get("placeholders"), repair.patch)
    try:
        repair.patched = apply(run.payload, repair.patch)
    except PatchError as exc:
        repair.skipped = f"the proposed patch cannot be applied as written: {exc}"
        return repair
    repair.outcome = revalidate(run, repair.patched)
    _settle_target(repair.outcome, finding)
    return repair


def write_out(repair: Repair, run: Run, out: Path) -> str:
    """Write the patched copy to ``out``; refuse the original or any resolve path."""
    target = out.resolve()
    protected = [run.document.resolve(), *(p.resolve() for p in run.resolve)]
    if any(target == p or (p.is_dir() and target.is_relative_to(p)) for p in protected):
        return f"refused to write {out}: it is the original document or a --resolve path"
    if repair.patched is None:
        return f"nothing written to {out}: no applicable patch"
    out.write_text(
        json.dumps(repair.patched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return f"patched copy written to {out}; the original was not touched"


def _render_outcome(outcome: Outcome, label: str) -> list[str]:
    lines = ["  re-validation by the deterministic validator:"]
    lines.append(
        f"    {'resolves' if outcome.resolved else 'does NOT resolve'} {label}; "
        f"{outcome.unchanged} finding(s) untouched; "
        f"{len(outcome.also_resolved)} other(s) also resolved; "
        f"{len(outcome.changed)} changed; {len(outcome.introduced)} introduced"
    )
    for f in outcome.also_resolved:
        lines.append(f"    also resolved: {f.severity.value} {f.code} at={f.location}")
    for before, after in outcome.changed:
        lines.append(
            f"    changed: {before.severity.value} {before.code} at={before.location}: "
            f"{before.prop} = {before.value} -> {after.value}"
        )
    for f in outcome.introduced:
        lines.append(
            f"    introduced: {f.severity.value} {f.code} at={f.location} ({f.prop} = {f.value})"
        )
    summary_before = ", ".join(f"{v} {k}" for k, v in outcome.before.items())
    summary_after = ", ".join(f"{v} {k}" for k, v in outcome.after.items())
    lines.append(f"    before: {summary_before}")
    lines.append(f"    after:  {summary_after}")
    return lines


def render_text(repair: Repair) -> str:
    lines = [f"== {repair.label}", repair.finding.render_text(), ""]
    v = repair.verified
    if v is not None:
        lines.append(
            f"  rationale ({len(v.quotes)} quote(s) verified, {len(v.withheld_quotes)} withheld, "
            f"{len(v.withheld_sentences)} sentence(s) withheld):"
        )
        if v.refused:
            lines.append(f"  refused: {v.refusal}")
        lines.extend(f"  {p}" if p else "" for p in v.prose.split("\n"))
        if v.quotes:
            lines.append("  quotes:")
            lines.append(render_quotes(v.quotes))
        withheld = render_withheld(v)
        if withheld:
            lines.append("  withheld:")
            lines.append(withheld)
    if repair.skipped:
        lines.append(f"  no draft: {repair.skipped}")
        return "\n".join(lines)
    lines.append("  proposed patch (RFC 6902, not applied):")
    lines.extend(f"    {json.dumps(op.to_dict(), ensure_ascii=False)}" for op in repair.patch)
    for placeholder in repair.placeholders:
        lines.append(f"  placeholder at {placeholder['path']}: {placeholder['why']}")
    if repair.outcome is not None:
        lines.extend(_render_outcome(repair.outcome, repair.label))
        lines.append(
            "  diff (against a canonical re-serialization of the document, 2-space indent):"
        )
        lines.extend(f"    {line}" for line in repair.outcome.diff.split("\n"))
    return "\n".join(lines)


def render_json(repairs: list[Repair], client: ModelClient, run: Run) -> dict[str, Any]:
    served = next((r.served_model for r in repairs if r.served_model), None)
    return {
        "command": "repair",
        "document": {"path": run.document.name, "model": run.model},
        "provenance": provenance(client, served),
        "drafts": [r.to_dict() for r in repairs],
    }
