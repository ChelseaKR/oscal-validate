"""``walkthrough``: where to start on a long report, without inventing or hiding anything.

The ordering is the tool's, not the model's. Findings are grouped by the
structural dependency between them -- an import that was not supplied has
to come before the references it leaves unsettled, a subtree the validator
could not read before anything under it, identifiers before the references
that name them -- and each group is labeled G1..Gn with its findings'
labels inside it. The model writes the narrative over those labels and
nothing else.

After generation two checks run that do not involve a model. A label the
narrative uses that the validator did not produce is struck from the text
and counted. A group the narrative never mentions is appended under its own
heading, with every finding in it, so the walkthrough covers the whole
report whether or not the model did. Then the guard screens every sentence.
The full index of findings by group is printed last, so nothing the
validator said is absent from what the reader holds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..findings import Finding
from . import guard, prompts
from .client import ModelClient, ModelError
from .run import Run, provenance
from .verify import ReplyError, parse_reply

#: Fix order. Each tier names the codes in it and why it comes where it does.
TIERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "Supply what the document imports",
        "an import that was not supplied, or matched more than one file, leaves every "
        "reference into it unsettled; nothing below can be decided until this is",
        ("IMPORT_NOT_SUPPLIED", "IMPORT_AMBIGUOUS"),
    ),
    (
        "Shape the validator could not read",
        "a subtree the schema walk could not resolve, an object no alternative accepts, or "
        "a value of the wrong JSON type hides everything beneath it from every later check",
        ("SUBTREE_NOT_READ", "NO_SCHEMA_ALTERNATIVE", "TYPE_MISMATCH"),
    ),
    (
        "Required structure",
        "properties the schema requires, forbids, or bounds",
        ("REQUIRED_PROPERTY_MISSING", "PROPERTY_UNDECLARED", "ARRAY_TOO_SHORT"),
    ),
    (
        "Values against their datatypes",
        "a malformed UUID or timestamp is also a broken identifier or a broken sort key",
        ("DATATYPE_MISMATCH", "DATATYPE_BELOW_MINIMUM"),
    ),
    (
        "Identifiers",
        "a duplicated id cannot be referenced unambiguously, so these come before references",
        ("UUID_NOT_UNIQUE", "CONSTRAINT_NOT_UNIQUE", "CONSTRAINT_CARDINALITY"),
    ),
    (
        "References that resolve to nothing",
        "the effective data model is complete and the target does not exist",
        ("REFERENCE_UNRESOLVED",),
    ),
    (
        "Declared version",
        "the document was judged against OSCAL 1.2.3 whatever it declares (issue #8)",
        ("OSCAL_VERSION_DIFFERS",),
    ),
    (
        "Not settled: UNVERIFIABLE",
        "neither a pass nor a fail; what would settle each is named in the finding",
        ("REFERENCE_UNVERIFIABLE", "CONSTRAINT_NOT_EVALUATED", "PATTERN_NOT_CHECKED"),
    ),
    (
        "For the record",
        "imports that were matched, listed so the effective data model is visible",
        ("IMPORT_RESOLVED",),
    ),
)

EXAMPLES_PER_GROUP = 3
NOT_COVERED = "Not covered by the narrative"


@dataclass
class Group:
    label: str
    tier: str
    why: str
    code: str
    severity: str
    findings: list[Finding]

    def summary_line(self, run: Run) -> str:
        return f"{self.label}: {self.severity} {self.code} x{len(self.findings)} ({self.tier})"

    def prompt_block(self, run: Run) -> str:
        lines = [f"{self.label}  {self.severity} {self.code}  {len(self.findings)} finding(s)"]
        lines.append(f"    tier: {self.tier} -- {self.why}")
        for finding in self.findings[:EXAMPLES_PER_GROUP]:
            lines.append(
                f"    {run.label(finding)} at={finding.location} {finding.prop}="
                f"{finding.value[:60]}: {finding.message[:160]}"
            )
        if len(self.findings) > EXAMPLES_PER_GROUP:
            lines.append(
                f"    ... and {len(self.findings) - EXAMPLES_PER_GROUP} more in {self.label}"
            )
        return "\n".join(lines)


def group(run: Run) -> list[Group]:
    """Every finding into exactly one group, in fix order, labeled G1..Gn."""
    known = {code: (tier, why) for tier, why, codes in TIERS for code in codes}
    order = {code: index for index, (_, _, codes) in enumerate(TIERS) for code in codes}
    buckets: dict[str, list[Finding]] = {}
    for finding in run.findings:
        buckets.setdefault(finding.code, []).append(finding)
    codes = sorted(buckets, key=lambda c: (order.get(c, len(TIERS)), c))
    groups: list[Group] = []
    for index, code in enumerate(codes, 1):
        tier, why = known.get(
            code, ("Other", "a code this grouping does not know; fix order unstated")
        )
        findings = buckets[code]
        severity = max((f.severity.value for f in findings), key=_severity_rank)
        groups.append(Group(f"G{index}", tier, why, code, severity, findings))
    return groups


def _severity_rank(value: str) -> int:
    return {"ERROR": 3, "WARNING": 2, "INFO": 1, "UNVERIFIABLE": 0}.get(value, -1)


_LABEL = re.compile(r"\b([GF]\d+)\b")


@dataclass
class Walkthrough:
    groups: list[Group]
    overview: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    closing: str = ""
    refused: bool = False
    refusal: str = ""
    invented: list[str] = field(default_factory=list)
    not_covered: list[Group] = field(default_factory=list)
    withheld_sentences: int = 0
    skipped: str = ""
    served_model: str = ""

    @property
    def covered(self) -> int:
        return len(self.groups) - len(self.not_covered)

    def to_dict(self, run: Run) -> dict[str, Any]:
        out: dict[str, Any] = {
            "groups": [
                {
                    "label": g.label,
                    "tier": g.tier,
                    "code": g.code,
                    "severity": g.severity,
                    "count": len(g.findings),
                    "findings": [run.label(f) for f in g.findings],
                }
                for g in self.groups
            ]
        }
        if self.skipped:
            out["skipped"] = self.skipped
            return out
        out.update(
            {
                "refused": self.refused,
                "refusal": self.refusal,
                "overview": self.overview,
                "steps": self.steps,
                "closing": self.closing,
                "invented_labels": self.invented,
                "not_covered": [g.label for g in self.not_covered],
                "groups_covered": self.covered,
                "withheld_sentences": self.withheld_sentences,
            }
        )
        return out


def _strike(text: str, valid: set[str], invented: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        label = match.group(1)
        if label in valid:
            return label
        invented.append(label)
        return "[label struck: not a finding the validator produced]"

    return _LABEL.sub(replace, text)


def _screen(text: str, counter: list[int]) -> str:
    screened = guard.screen(text)
    counter[0] += screened.withheld_count
    return screened.text


def check(payload: dict[str, Any], run: Run, groups: list[Group]) -> Walkthrough:
    """Strike invented labels, find uncovered groups, screen every sentence."""
    valid = {g.label for g in groups} | set(run.labels.values())
    invented: list[str] = []
    withheld = [0]
    result = Walkthrough(groups=groups)
    result.refused = bool(payload.get("refused", False))
    result.refusal = _screen(
        _strike(str(payload.get("refusal", "") or ""), valid, invented), withheld
    )
    result.overview = _screen(
        _strike(str(payload.get("overview", "") or ""), valid, invented), withheld
    )
    result.closing = _screen(
        _strike(str(payload.get("closing", "") or ""), valid, invented), withheld
    )
    mentioned: set[str] = set()
    raw_steps = payload.get("steps")
    for raw in raw_steps if isinstance(raw_steps, list) else []:
        if not isinstance(raw, dict):
            continue
        labels = [str(x) for x in raw.get("labels", []) if isinstance(raw.get("labels"), list)]
        kept = [x for x in labels if x in valid]
        invented.extend(x for x in labels if x not in valid)
        text = _screen(_strike(str(raw.get("text", "") or ""), valid, invented), withheld)
        title = _screen(_strike(str(raw.get("title", "") or ""), valid, invented), withheld)
        mentioned.update(kept)
        mentioned.update(m.group(1) for m in _LABEL.finditer(text) if m.group(1) in valid)
        result.steps.append({"title": title, "labels": kept, "text": text})
    for text in (result.overview, result.closing):
        mentioned.update(m.group(1) for m in _LABEL.finditer(text) if m.group(1) in valid)
    finding_to_group = {run.label(f): g.label for g in groups for f in g.findings}
    covered_groups = {finding_to_group.get(m, m) for m in mentioned}
    result.not_covered = [g for g in groups if g.label not in covered_groups]
    result.invented = sorted(set(invented))
    result.withheld_sentences = withheld[0]
    return result


def walk(run: Run, client: ModelClient) -> Walkthrough:
    groups = group(run)
    if not groups:
        return Walkthrough(
            groups=[], skipped="the validator produced no findings; nothing to walk through"
        )
    blocks = "\n\n".join(g.prompt_block(run) for g in groups)
    user = prompts.walkthrough_user(run.model, blocks, run.notes_for())
    try:
        completion = client.complete(prompts.SYSTEM, user)
    except ModelError as exc:
        return Walkthrough(groups=groups, skipped=f"the model call failed: {exc}")
    try:
        payload = parse_reply(completion.text)
    except ReplyError as exc:
        return Walkthrough(
            groups=groups, skipped=f"the model's reply was unusable ({exc}); nothing shown"
        )
    result = check(payload, run, groups)
    result.served_model = completion.model
    return result


def render_index(groups: list[Group], run: Run) -> str:
    lines = ["index: every finding, by group, in the tool's fix order"]
    for g in groups:
        lines.append(f"  {g.label}  {g.severity} {g.code}  x{len(g.findings)}  [{g.tier}]")
        for finding in g.findings:
            value = finding.value[:80]
            lines.append(
                f"      {run.label(finding)} at={finding.location} {finding.prop} = {value}"
            )
    return "\n".join(lines)


def render_text(result: Walkthrough, run: Run, index: bool = True) -> str:
    lines: list[str] = []
    if result.skipped:
        lines.append(f"no walkthrough: {result.skipped}")
    else:
        lines.append(
            f"walkthrough ({result.covered} of {len(result.groups)} group(s) covered by the "
            f"narrative, {len(result.invented)} invented label(s) struck, "
            f"{result.withheld_sentences} sentence(s) withheld):"
        )
        if result.refused:
            lines.append(f"  refused: {result.refusal}")
        lines.append(f"  {result.overview}")
        for number, step in enumerate(result.steps, 1):
            labels = ", ".join(step["labels"]) if step["labels"] else "(no labels)"
            lines.append(f"\n  {number}. {step['title']}  [{labels}]")
            lines.extend(f"     {p}" if p else "" for p in step["text"].split("\n"))
        if result.closing:
            lines.append(f"\n  {result.closing}")
        if result.not_covered:
            lines.append(
                f"\n  {NOT_COVERED} (appended by the tool; the model did not mention these):"
            )
            for g in result.not_covered:
                lines.append(f"    {g.summary_line(run)}")
        if result.invented:
            lines.append(
                f"\n  struck: {', '.join(result.invented)} (labels the validator never produced)"
            )
    if index and result.groups:
        lines.append("")
        lines.append(render_index(result.groups, run))
    return "\n".join(lines)


def render_json(result: Walkthrough, client: ModelClient, run: Run) -> dict[str, Any]:
    return {
        "command": "walkthrough",
        "document": {"path": run.document.name, "model": run.model},
        "provenance": provenance(client, result.served_model or None),
        "walkthrough": result.to_dict(run),
    }
