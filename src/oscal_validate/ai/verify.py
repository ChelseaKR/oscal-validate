"""What sits between a model's reply and the reader.

Two checks, neither of which asks a model anything. Every quotation the
reply makes is looked up verbatim in the source it names; one that is not
there is withheld, its marker in the prose replaced by a note, and counted.
Then the prose itself goes through the boundary guard, which withholds any
sentence carrying an implementation, security, or authorization judgment.
What comes out is what the command prints, with both counts beside it.

The reply is expected to be one JSON object. A reply that is not parseable
is reported as such and nothing from it is shown: a half-parsed answer is
the kind of thing that reads as more than it is.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from . import guard, sources


class ReplyError(ValueError):
    """The model's reply could not be read as the contract it was asked for."""


def parse_reply(text: str) -> dict[str, Any]:
    """The one JSON object in a reply, tolerating a code fence around it."""
    stripped = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end < start:
        raise ReplyError("the reply contains no JSON object")
    try:
        payload: dict[str, Any] = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ReplyError(f"the reply is not valid JSON: {exc.msg}") from exc
    return payload


@dataclass(frozen=True)
class Quote:
    identifier: str
    source: str
    text: str
    url: str
    retrieved: str


@dataclass(frozen=True)
class Withheld:
    identifier: str
    source: str
    reason: str


@dataclass
class Verified:
    """Prose with its quotes checked and its sentences screened."""

    refused: bool
    refusal: str
    prose: str
    quotes: list[Quote] = field(default_factory=list)
    withheld_quotes: list[Withheld] = field(default_factory=list)
    withheld_sentences: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.withheld_quotes and not self.withheld_sentences


_MARKER = re.compile(r"\[(Q\d+)\]")
#: A quotation written inline in the prose, long enough to be a claim about
#: what a source says rather than a term being mentioned.
#: It must read as a sentence: it starts with a capital letter and contains no
#: backtick, brace, or line break, so that a JSON literal such as ``"id":
#: "ex-1"`` written into the prose is never mistaken for the start of one.
_INLINE = re.compile(r"[\"\u201c]([A-Z][^\"\u201c\u201d`{}\n]{39,}?)[\"\u201d]")
INLINE_WITHHELD = "[unverified quotation withheld]"


def _quotes(raw: Any) -> tuple[list[Quote], list[Withheld]]:
    verified: list[Quote] = []
    withheld: list[Withheld] = []
    if not isinstance(raw, list):
        return verified, withheld
    for item in raw:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("id", "")).strip()
        source = str(item.get("source", "")).strip()
        text = str(item.get("text", "")).strip()
        loaded = sources.load(source)
        if loaded is None:
            withheld.append(Withheld(identifier, source, "names a source that does not exist"))
        elif len(sources.normalize(text)) < sources.MIN_QUOTE_CHARS:
            withheld.append(Withheld(identifier, source, "too short to verify"))
        elif not sources.contains(source, text):
            withheld.append(Withheld(identifier, source, "not found verbatim in that source"))
        else:
            verified.append(Quote(identifier, source, text, loaded.url, loaded.retrieved))
    return verified, withheld


def _strike_markers(prose: str, known: set[str], withheld: set[str]) -> tuple[str, list[Withheld]]:
    """Replace markers for withheld or unknown quotes with a note, in place."""
    extra: list[Withheld] = []

    def replace(match: re.Match[str]) -> str:
        identifier = match.group(1)
        if identifier in known:
            return match.group(0)
        if identifier not in withheld:
            extra.append(Withheld(identifier, "", "cited but never supplied"))
        return f"[quote {identifier} withheld]"

    return _MARKER.sub(replace, prose), extra


def _strike_inline(prose: str) -> tuple[str, list[Withheld]]:
    """A quotation written inline is held to the same standard as a cited one."""
    struck: list[Withheld] = []

    def replace(match: re.Match[str]) -> str:
        if sources.locate(match.group(1)):
            return match.group(0)
        struck.append(
            Withheld("", "", f"inline quotation not found in any source: {match.group(1)[:40]}...")
        )
        return INLINE_WITHHELD

    return _INLINE.sub(replace, prose), struck


def verify(payload: dict[str, Any], prose_field: str) -> Verified:
    """Check one reply's quotes and screen its prose. Never raises on content."""
    refused = bool(payload.get("refused", False))
    refusal = str(payload.get("refusal", "") or "")
    prose = str(payload.get(prose_field, "") or "")
    quotes, withheld = _quotes(payload.get("quotes"))
    prose, extra = _strike_markers(
        prose, {q.identifier for q in quotes}, {w.identifier for w in withheld}
    )
    withheld.extend(extra)
    prose, inline = _strike_inline(prose)
    withheld.extend(inline)
    screened = guard.screen(prose)
    screened_refusal = guard.screen(refusal)
    return Verified(
        refused=refused,
        refusal=screened_refusal.text,
        prose=screened.text,
        quotes=quotes,
        withheld_quotes=withheld,
        withheld_sentences=[*screened.withheld, *screened_refusal.withheld],
        extra={
            k: v
            for k, v in payload.items()
            if k not in {prose_field, "quotes", "refused", "refusal"}
        },
    )


def render_quotes(quotes: list[Quote]) -> str:
    lines: list[str] = []
    for quote in quotes:
        lines.append(f'  [{quote.identifier}] "{quote.text}"')
        lines.append(f"       — {quote.source}: {quote.url} (retrieved {quote.retrieved})")
    return "\n".join(lines)


def render_withheld(verified: Verified) -> str:
    lines: list[str] = []
    for item in verified.withheld_quotes:
        where = f" from {item.source}" if item.source else ""
        lines.append(f"  quote {item.identifier or '?'} withheld{where}: {item.reason}")
    if verified.withheld_sentences:
        count = len(verified.withheld_sentences)
        lines.append(
            f"  {count} sentence(s) withheld by the boundary guard: a judgment about "
            "implementation, security, or authorization"
        )
    return "\n".join(lines)
