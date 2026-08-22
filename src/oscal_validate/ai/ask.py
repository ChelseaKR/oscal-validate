"""``ask``: what a constraint requires and why NIST has it, from the corpus.

A free-text question, answered from the corpus passages that bear on it and
nothing else, through the same verifier and guard as ``explain``. With a
document supplied, the validator runs first and the model is shown a
compact list of its findings, so "what is wrong with my profile" is
answered from the findings and not from the model's imagination. Without a
document there are no findings, and the answer says so if the question
needs them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import prompts, sources
from .client import ModelClient, ModelError
from .run import Run, provenance
from .verify import ReplyError, Verified, parse_reply, render_quotes, render_withheld, verify

#: How many findings a question's context lists before it says "and N more".
FINDINGS_SHOWN = 40


@dataclass
class Answer:
    question: str
    verified: Verified | None
    skipped: str = ""
    served_model: str = ""
    passages: list[sources.Passage] | None = None
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"question": self.question}
        if self.skipped:
            out["skipped"] = self.skipped
            return out
        v = self.verified
        assert v is not None  # noqa: S101 - invariant: not skipped means verified
        out.update(
            {
                "refused": v.refused,
                "refusal": v.refusal,
                "answer": v.prose,
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
                "evidence": [{"source": p.source, "section": p.label} for p in self.passages or []],
            }
        )
        return out


def findings_context(run: Run) -> str:
    lines = [f"Document model: {run.model}; {len(run.findings)} finding(s) from the validator."]
    for finding in run.findings[:FINDINGS_SHOWN]:
        lines.append(
            f"  {run.label(finding)} {finding.severity.value} {finding.code} at={finding.location}"
            f" {finding.prop}={finding.value[:80]}"
        )
    if len(run.findings) > FINDINGS_SHOWN:
        lines.append(f"  ... and {len(run.findings) - FINDINGS_SHOWN} more")
    for note in run.notes_for():
        lines.append(f"  note: {note}")
    return "\n".join(lines)


def ask_one(question: str, client: ModelClient, run: Run | None = None) -> Answer:
    model = run.model if run is not None else None
    passages = sources.passages_for_question(question, model)
    context = findings_context(run) if run is not None else None
    user = prompts.ask_user(question, model, passages, context)
    try:
        completion = client.complete(prompts.SYSTEM, user)
    except ModelError as exc:
        return Answer(question, None, skipped=f"the model call failed: {exc}")
    try:
        payload = parse_reply(completion.text)
    except ReplyError as exc:
        return Answer(
            question, None, skipped=f"the model's reply was unusable ({exc}); nothing shown"
        )
    return Answer(
        question=question,
        verified=verify(payload, "explanation"),
        served_model=completion.model,
        passages=passages,
        raw=payload,
    )


def render_text(answer: Answer) -> str:
    lines = [f"question: {answer.question}", ""]
    if answer.skipped:
        lines.append(f"  not answered: {answer.skipped}")
        return "\n".join(lines)
    v = answer.verified
    assert v is not None  # noqa: S101 - invariant: not skipped means verified
    lines.append(
        f"  answer ({len(v.quotes)} quote(s) verified, {len(v.withheld_quotes)} withheld, "
        f"{len(v.withheld_sentences)} sentence(s) withheld):"
    )
    if v.refused:
        lines.append(f"  refused: {v.refusal}")
    for paragraph in v.prose.split("\n"):
        lines.append(f"  {paragraph}" if paragraph else "")
    if v.quotes:
        lines.append("  quotes:")
        lines.append(render_quotes(v.quotes))
    withheld = render_withheld(v)
    if withheld:
        lines.append("  withheld:")
        lines.append(withheld)
    return "\n".join(lines)


def render_json(answer: Answer, client: ModelClient, run: Run | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "command": "ask",
        "provenance": provenance(client, answer.served_model or None),
        "answer": answer.to_dict(),
    }
    if run is not None:
        out["document"] = {"path": run.document.name, "model": run.model}
    return out
