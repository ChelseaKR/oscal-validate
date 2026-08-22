"""``explain``: one finding, in plain language, grounded in NIST's text.

For each selected finding the command gathers the evidence ``sources`` can
find for it, asks the model for an explanation that quotes that evidence,
verifies every quote, screens every sentence, and prints the result under
the finding itself. A finding for which no evidence exists is not sent to
the model at all; the command says so and moves on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..findings import Finding
from . import prompts, sources
from .client import ModelClient, ModelError
from .run import Run, provenance
from .verify import ReplyError, Verified, parse_reply, render_quotes, render_withheld, verify


@dataclass
class Explanation:
    label: str
    finding: Finding
    verified: Verified | None
    skipped: str = ""
    served_model: str = ""
    passages: list[sources.Passage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"label": self.label, "finding": self.finding.to_dict()}
        if self.skipped:
            out["skipped"] = self.skipped
            return out
        assert self.verified is not None  # noqa: S101 - invariant: not skipped means verified
        v = self.verified
        out.update(
            {
                "refused": v.refused,
                "refusal": v.refusal,
                "explanation": v.prose,
                "next_step": str(v.extra.get("next_step", "") or ""),
                "quotes": [
                    {
                        "id": q.identifier,
                        "source": q.source,
                        "text": q.text,
                        "url": q.url,
                        "retrieved": q.retrieved,
                    }
                    for q in v.quotes
                ],
                "withheld_quotes": [
                    {"id": w.identifier, "source": w.source, "reason": w.reason}
                    for w in v.withheld_quotes
                ],
                "withheld_sentences": len(v.withheld_sentences),
                "evidence": [{"source": p.source, "section": p.label} for p in self.passages],
            }
        )
        return out


def explain_one(run: Run, finding: Finding, client: ModelClient) -> Explanation:
    label = run.label(finding)
    passages = sources.passages_for_finding(finding, run.model)
    if not passages:
        return Explanation(
            label=label,
            finding=finding,
            verified=None,
            skipped=(
                "no source in the corpus resolves this finding's rule, so there is nothing to "
                "quote and no explanation was generated"
            ),
        )
    user = prompts.explain_user(
        finding.to_dict(),
        run.model,
        run.excerpt(finding.location),
        passages,
        run.notes_for(finding),
    )
    try:
        completion = client.complete(prompts.SYSTEM, user)
    except ModelError as exc:
        return Explanation(label, finding, None, skipped=f"the model call failed: {exc}")
    try:
        payload = parse_reply(completion.text)
    except ReplyError as exc:
        return Explanation(
            label, finding, None, skipped=f"the model's reply was unusable ({exc}); nothing shown"
        )
    return Explanation(
        label=label,
        finding=finding,
        verified=verify(payload, "explanation"),
        served_model=completion.model,
        passages=passages,
    )


def render_text(explanation: Explanation) -> str:
    lines = [f"== {explanation.label}", explanation.finding.render_text(), ""]
    if explanation.skipped:
        lines.append(f"  not explained: {explanation.skipped}")
        return "\n".join(lines)
    v = explanation.verified
    assert v is not None  # noqa: S101 - invariant: not skipped means verified
    header = (
        f"  explanation ({len(v.quotes)} quote(s) verified, "
        f"{len(v.withheld_quotes)} withheld, {len(v.withheld_sentences)} sentence(s) withheld):"
    )
    lines.append(header)
    if v.refused:
        lines.append(f"  refused: {v.refusal}")
    for paragraph in v.prose.split("\n"):
        lines.append(f"  {paragraph}" if paragraph else "")
    if v.quotes:
        lines.append("  quotes:")
        lines.append(render_quotes(v.quotes))
    next_step = str(v.extra.get("next_step", "") or "")
    if next_step:
        lines.append(f"  next step: {next_step}")
    withheld = render_withheld(v)
    if withheld:
        lines.append("  withheld:")
        lines.append(withheld)
    return "\n".join(lines)


def render_json(explanations: list[Explanation], client: ModelClient, run: Run) -> dict[str, Any]:
    served = next((e.served_model for e in explanations if e.served_model), None)
    return {
        "command": "explain",
        "document": {"path": run.document.name, "model": run.model},
        "provenance": provenance(client, served),
        "explanations": [e.to_dict() for e in explanations],
    }
