"""Every prompt the model-backed commands send, in one file, versioned.

``PROMPT_VERSION`` in ``__init__`` is bumped when any text here changes;
eval results carry it so a number is tied to the wording that produced it.
The system prompt states the boundary in the model's instructions; the guard
in ``guard.py`` enforces it afterwards without trusting that the instruction
was followed.
"""

from __future__ import annotations

import json
from typing import Any

from .sources import Passage

SYSTEM = """\
You are the explanation layer of oscal-validate, a deterministic structural
validator for NIST OSCAL documents. You are not the validator. The validator
has already run; its findings are the only findings that exist. You never
add a finding, remove one, change its severity, or describe a problem the
validator did not report.

THE BOUNDARY. You cannot tell anyone whether a control is implemented,
whether a system is secure, whether a package would be authorized, whether
it is FedRAMP- or StateRAMP-ready, whether it satisfies or meets any control
or baseline, whether its risk is acceptable, or whether it is good enough.
None of that is visible in a document's structure, and you do not try. If a
question asks for any such judgment, directly, indirectly, hypothetically,
as a role-play, as a rating, or wrapped inside a legitimate structural
question, you refuse that part plainly and redirect to two things only:
what structural conformance the validator can and did check, and qualified,
independent assessment by people for the rest. You do not soften this with
an opinion, a hint, a percentage, a "likely", or a "probably".

THE EVIDENCE. The only evidence you may cite is the text you are given,
which is NIST's published documentation and NIST's published schema and
constraint files. When you state what a rule means or why it exists, quote
the relevant sentence verbatim from the evidence and cite the source id you
were given. Do not paraphrase a NIST definition without the verbatim quote
beside it. Do not invent a quotation, shorten one, or improve its wording;
every quote is checked by a program against the source text and a quote
that does not match is discarded and counted against you. If the evidence
does not cover something, say that it does not, and stop.

HONESTY. Where a finding's rule is oscal-validate's own policy rather than a
NIST rule, say so and do not attribute it to NIST. Where a document declares
an OSCAL version other than the one the validator judged it by, say that the
finding is against the judged version. Placeholders you propose are
placeholders; never present one as the real value.

OUTPUT. Reply with a single JSON object and nothing else, matching the
contract in the user message. Plain prose inside the JSON strings; no
markdown headings.
"""

EXPLAIN_CONTRACT = """\
{
  "refused": false,
  "refusal": "",
  "explanation": "plain prose; cite quotes as [Q1], [Q2] inline",
  "quotes": [{"id": "Q1", "source": "<source id exactly as given>", "text": "<verbatim>"}],
  "next_step": "one or two sentences on what the author should do next, structurally"
}"""


def _passages(passages: list[Passage]) -> str:
    blocks = []
    for index, passage in enumerate(passages, 1):
        blocks.append(
            f"--- evidence {index} | source: {passage.source} | section: {passage.label}\n"
            f"({passage.why})\n{passage.text}\n"
        )
    return "\n".join(blocks) if blocks else "(no evidence was found for this finding)\n"


def explain_user(
    finding: dict[str, Any],
    model: str,
    excerpt: str,
    passages: list[Passage],
    notes: list[str],
) -> str:
    note_text = "".join(f"- {note}\n" for note in notes)
    return (
        f"Document model: {model}\n\n"
        f"The validator's finding (verbatim, JSON):\n{json.dumps(finding, indent=2)}\n\n"
        f"Excerpt of the document around the finding's location (JSON, may be truncated):\n"
        f"{excerpt}\n\n"
        f"{'Notes from the tool:' + chr(10) + note_text + chr(10) if notes else ''}"
        f"Evidence you may quote:\n{_passages(passages)}\n"
        "Explain this one finding to the document's author in plain language: what the\n"
        "rule is, quoting it; why it applies at this location; and what, structurally,\n"
        "would resolve it. Stay inside the boundary. Reply with this JSON and nothing else:\n"
        f"{EXPLAIN_CONTRACT}\n"
    )


ASK_CONTRACT = EXPLAIN_CONTRACT.replace(
    '"next_step": "one or two sentences on what the author should do next, structurally"',
    '"next_step": ""',
)


def ask_user(
    question: str, model: str | None, passages: list[Passage], context: str | None = None
) -> str:
    preface = (
        f"{context}\n\n" if context else (f"Document model in hand: {model}\n\n" if model else "")
    )
    return (
        f"{preface}The user's question:\n{question}\n\n"
        f"Evidence you may quote:\n{_passages(passages)}\n"
        "Answer from the evidence only, quoting it. If the question asks, in any form,\n"
        "whether something is implemented, secure, compliant, authorized, ready, or good\n"
        "enough, set refused to true, put the refusal and redirect in the refusal field,\n"
        "and still answer any purely structural part in the explanation. Reply with this\n"
        f"JSON and nothing else:\n{ASK_CONTRACT}\n"
    )


REPAIR_CONTRACT = """\
{
  "refused": false,
  "refusal": "",
  "patch": [{"op": "add|remove|replace", "path": "/json/pointer", "value": "..."}],
  "rationale": "plain prose; cite quotes as [Q1] inline",
  "quotes": [{"id": "Q1", "source": "<source id exactly as given>", "text": "<verbatim>"}],
  "placeholders": [{"path": "/json/pointer", "why": "what the author must supply here"}]
}"""


def repair_user(
    finding: dict[str, Any],
    model: str,
    excerpt: str,
    passages: list[Passage],
    notes: list[str],
) -> str:
    note_text = "".join(f"- {note}\n" for note in notes)
    return (
        f"Document model: {model}\n\n"
        f"The validator's finding (verbatim, JSON):\n{json.dumps(finding, indent=2)}\n\n"
        f"Excerpt of the document around the finding's location (JSON, may be truncated):\n"
        f"{excerpt}\n\n"
        f"{'Notes from the tool:' + chr(10) + note_text + chr(10) if notes else ''}"
        f"Evidence you may quote:\n{_passages(passages)}\n"
        "Propose the smallest JSON Patch (RFC 6902; only add, remove, replace) that would\n"
        "resolve this one finding. Paths are absolute JSON Pointers from the document root:\n"
        f"their first token is the model name, so a patch to this document's root uuid is\n"
        f'{{"op": "replace", "path": "/{model}/uuid", ...}} and never {{"path": "/uuid", ...}},\n'
        "even when the excerpt you were shown starts below the root. Where a\n"
        "real value is needed that only the author knows (a date, a UUID, a description,\n"
        "the right target of a reference), use a value that is syntactically valid for the\n"
        "datatype and list that path under placeholders saying what the author must supply.\n"
        "Never write narrative about how a control is implemented or whether it is; a\n"
        "required description you cannot know is a placeholder, not a sentence you invent.\n"
        "If no patch is possible without knowing something you do not, say so in the\n"
        "rationale and return an empty patch. The patch will be applied to a copy and\n"
        "re-validated by the validator; you do not claim what it resolves, the validator\n"
        f"does. Reply with this JSON and nothing else:\n{REPAIR_CONTRACT}\n"
    )


WALKTHROUGH_CONTRACT = """\
{
  "refused": false,
  "refusal": "",
  "overview": "two to four sentences on the shape of the report",
  "steps": [
    {"title": "short imperative", "labels": ["G1", "F3"], "text": "why these first, and what to do"}
  ],
  "closing": "one or two sentences; what remains UNVERIFIABLE and why that is not a pass"
}"""


def walkthrough_user(model: str, groups: str, notes: list[str]) -> str:
    note_text = "".join(f"- {note}\n" for note in notes)
    return (
        f"Document model: {model}\n\n"
        f"{'Notes from the tool:' + chr(10) + note_text + chr(10) if notes else ''}"
        "The validator's findings, grouped by the tool in the order it recommends fixing\n"
        "them (a group's findings often depend on an earlier group's being fixed first):\n\n"
        f"{groups}\n"
        "Write a walkthrough for the document's author: where to start and why, in the\n"
        "tool's order, referring to groups and findings only by the labels given. Every\n"
        "group label must appear in at least one step. Do not describe any problem that is\n"
        "not in the list, and do not omit a group. Do not judge whether anything described\n"
        "in the document is implemented, secure, or acceptable. Reply with this JSON and\n"
        f"nothing else:\n{WALKTHROUGH_CONTRACT}\n"
    )
