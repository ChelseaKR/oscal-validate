"""NIST's published text, as the only evidence a model may quote.

Two kinds of source live here. ``corpus/`` holds text extracted from NIST's
pages by ``tools/corpus_fetch.py``, each with its URL, retrieval date, and
hashes in ``corpus/MANIFEST.json``. The vendored schema and metaschema files
under ``vendor/`` are sources too, under ids of the form ``vendor:<file>``,
with the hashes ``vendor/SOURCES.md`` already enforces.

Three things are built on top of the raw text. Sections: each corpus page is
split at its headings, and a reference page's nested headings are the JSON
names of the model, so a finding's location pointer maps to the section that
describes that element. Passages: a small, budgeted set of sections chosen
for one finding or one question, which is what the model is shown. And the
verifier's substrate: ``contains`` says whether a quote occurs verbatim in a
named source, after one normalization (whitespace collapsed, typographic
quotes straightened) that is applied to both sides.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from ..findings import Finding
from ..rules import IDENTIFIER_USE_URL, SCHEMA_URL, URI_USE_URL

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
VENDOR_DIR = Path(__file__).resolve().parent.parent / "vendor" / "oscal"
VENDOR_RELEASE_URL = "https://github.com/usnistgov/OSCAL/releases/tag/v1.2.3"
VENDOR_RETRIEVED = "2026-08-14"

#: A quote shorter than this proves nothing and is not accepted.
MIN_QUOTE_CHARS = 20

#: Which reference page describes which model root.
REFERENCE_FOR_MODEL = {
    "catalog": "reference-catalog",
    "profile": "reference-profile",
    "component-definition": "reference-component-definition",
    "system-security-plan": "reference-system-security-plan",
    "assessment-plan": "reference-assessment-plan",
    "assessment-results": "reference-assessment-results",
    "plan-of-action-and-milestones": "reference-plan-of-action-and-milestones",
}

CONCEPT_FOR_MODEL = {
    "catalog": "model-catalog",
    "profile": "model-profile",
    "component-definition": "model-component-definition",
    "system-security-plan": "model-ssp",
    "assessment-plan": "model-assessment-plan",
    "assessment-results": "model-assessment-results",
    "plan-of-action-and-milestones": "model-poam",
}

#: Rule URLs in ``rules.py`` -> the corpus page that text came from.
SOURCE_FOR_URL = {
    IDENTIFIER_USE_URL: "identifier-use",
    URI_USE_URL: "uri-use",
}


@dataclass(frozen=True)
class Source:
    identifier: str
    url: str
    title: str
    retrieved: str
    text: str

    @property
    def normalized(self) -> str:
        return normalize(self.text)


@dataclass(frozen=True)
class Section:
    source: str
    path: tuple[str, ...]
    heading: str
    text: str

    @property
    def label(self) -> str:
        return "/".join(self.path) if self.path else self.heading


@dataclass(frozen=True)
class Passage:
    """One piece of evidence shown to the model, with the id it must cite."""

    source: str
    label: str
    text: str
    why: str


_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTES)).strip()


@cache
def manifest() -> dict[str, dict[str, str]]:
    payload = json.loads((CORPUS_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    sources: dict[str, dict[str, str]] = payload["sources"]
    return sources


@cache
def load(identifier: str) -> Source | None:
    """A source by id, or None when no such source exists. Never a guess."""
    if identifier.startswith("vendor:"):
        path = VENDOR_DIR / identifier.removeprefix("vendor:")
        if not path.is_file() or path.parent != VENDOR_DIR:
            return None
        return Source(
            identifier=identifier,
            url=VENDOR_RELEASE_URL,
            title=path.name,
            retrieved=VENDOR_RETRIEVED,
            text=path.read_text(encoding="utf-8"),
        )
    entry = manifest().get(identifier)
    if entry is None:
        return None
    return Source(
        identifier=identifier,
        url=entry["url"],
        title=entry["title"],
        retrieved=entry["retrieved"],
        text=(CORPUS_DIR / f"{identifier}.txt").read_text(encoding="utf-8"),
    )


def source_ids() -> list[str]:
    vendored = sorted(f"vendor:{p.name}" for p in VENDOR_DIR.iterdir() if p.is_file())
    return sorted(manifest()) + vendored


def contains(identifier: str, quote: str) -> bool:
    """True when the quote occurs verbatim (after normalization) in that source."""
    source = load(identifier)
    if source is None:
        return False
    needle = normalize(quote)
    return len(needle) >= MIN_QUOTE_CHARS and needle in source.normalized


def locate(quote: str) -> list[str]:
    """Every source the quote occurs in. Empty means nowhere."""
    return [identifier for identifier in source_ids() if contains(identifier, quote)]


# -- sections ---------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6}) (.+)$")


@cache
def sections(identifier: str) -> tuple[Section, ...]:
    source = load(identifier)
    if source is None:
        return ()
    out: list[Section] = []
    stack: list[str] = []
    heading = "(preamble)"
    path: tuple[str, ...] = ()
    body: list[str] = []

    def flush() -> None:
        text = "\n".join(body).strip()
        if text:
            out.append(Section(source=identifier, path=path, heading=heading, text=text))

    for line in source.text.split("\n"):
        match = _HEADING.match(line)
        if match is None:
            body.append(line)
            continue
        flush()
        level = len(match.group(1))
        heading = match.group(2).strip()
        del stack[level - 1 :]
        stack.append(heading)
        path = tuple(stack)
        body = []
    flush()
    return tuple(out)


def _pointer_path(location: str) -> tuple[str, ...]:
    """``/catalog/groups/16/controls/23/id`` -> ``('catalog','groups','controls','id')``."""
    return tuple(
        segment.replace("~1", "/").replace("~0", "~")
        for segment in location.strip("/").split("/")
        if segment and not segment.isdigit()
    )


def reference_section(model: str, location: str) -> Section | None:
    """The reference page's section for a location, or the nearest ancestor's."""
    page = REFERENCE_FOR_MODEL.get(model)
    if page is None:
        return None
    by_path = {section.path: section for section in sections(page)}
    path = _pointer_path(location)
    while path:
        found = by_path.get(path)
        if found is not None:
            return found
        path = path[:-1]
    return None


# -- the vendored constraint layer ------------------------------------------

_CONSTRAINT_ID = re.compile(r"NIST OSCAL constraint (\S+) \(")
_MODULE = re.compile(r"in (oscal_[\w-]+_metaschema_RESOLVED\.xml)")
_DATATYPE = re.compile(r"^(\w+Datatype) in the vendored")


def constraint_snippet(identifier: str, module: str) -> str | None:
    """The XML element declaring one constraint, verbatim from the vendored file."""
    source = load(f"vendor:{module}")
    if source is None:
        return None
    match = re.search(
        rf"<(is-unique|index|index-has-key|has-cardinality|matches|expect|allowed-values)"
        rf"\b[^>]*\bid=\"{re.escape(identifier)}\"[^>]*(?:/>|>.*?</\1>)",
        source.text,
        re.DOTALL,
    )
    return match.group(0) if match else None


def _constraint_passages(finding: Finding) -> list[Passage]:
    citation = finding.rule.citation
    found_id = _CONSTRAINT_ID.search(citation)
    found_module = _MODULE.search(citation)
    if found_id is None or found_module is None:
        return []
    identifier, module = found_id.group(1), found_module.group(1)
    passages: list[Passage] = []
    snippet = constraint_snippet(identifier, module)
    if snippet is not None:
        passages.append(
            Passage(
                source=f"vendor:{module}",
                label=identifier,
                text=snippet,
                why="the constraint as NIST declared it, from the vendored metaschema module",
            )
        )
    kind = citation.split("(", 1)[1].split(",", 1)[0] if "(" in citation else ""
    passages.extend(_sections_matching("metaschema-constraints", kind, limit=2))
    return passages


def _sections_matching(identifier: str, needle: str, limit: int) -> list[Passage]:
    if not needle:
        return []
    needle = needle.lower()
    hits = [
        Passage(
            source=identifier,
            label=section.label,
            text=section.text,
            why=f"a section of the Metaschema specification mentioning {needle!r}",
        )
        for section in sections(identifier)
        if needle in section.heading.lower()
    ]
    return hits[:limit]


# -- retrieval --------------------------------------------------------------

_WORD = re.compile(r"[a-z][a-z0-9-]{2,}")
_STOP = frozenset(
    [
        "the",
        "and",
        "for",
        "this",
        "that",
        "with",
        "from",
        "into",
        "not",
        "are",
        "was",
        "were",
        "does",
        "which",
        "each",
        "any",
        "all",
        "one",
        "its",
        "has",
        "have",
        "had",
        "been",
        "being",
        "than",
        "then",
        "there",
        "their",
        "they",
        "them",
        "what",
        "when",
        "where",
        "who",
        "will",
        "can",
        "may",
        "must",
        "should",
        "would",
        "could",
        "also",
        "only",
        "such",
        "these",
        "those",
        "some",
        "more",
        "most",
        "under",
        "over",
        "here",
        "used",
        "use",
        "uses",
        "using",
        "value",
        "values",
        "document",
        "documents",
        "tool",
    ]
)


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def _keyword_passages(query: str, identifiers: list[str], limit: int) -> list[Passage]:
    terms = _terms(query)
    if not terms:
        return []
    scored: list[tuple[int, str, Section]] = []
    for identifier in identifiers:
        for section in sections(identifier):
            overlap = len(terms & _terms(section.heading + " " + section.text[:2000]))
            if overlap:
                scored.append((-overlap, section.label, section))
    scored.sort(key=lambda item: (item[0], item[2].source, item[1]))
    return [
        Passage(
            source=section.source,
            label=section.label,
            text=section.text,
            why="a section whose wording overlaps the finding",
        )
        for _, _, section in scored[:limit]
    ]


def _budget(passages: list[Passage], each: int, total: int) -> list[Passage]:
    out: list[Passage] = []
    seen: set[tuple[str, str]] = set()
    spent = 0
    for passage in passages:
        key = (passage.source, passage.label)
        if key in seen:
            continue
        text = passage.text[:each]
        if spent + len(text) > total:
            break
        seen.add(key)
        spent += len(text)
        out.append(Passage(passage.source, passage.label, text, passage.why))
    return out


def passages_for_finding(finding: Finding, model: str) -> list[Passage]:
    """The evidence for one finding, most specific first, within a byte budget."""
    passages: list[Passage] = []
    url_source = SOURCE_FOR_URL.get(finding.rule.url)
    if url_source is not None:
        passages.extend(_keyword_passages(finding.rule.citation, [url_source], limit=2))
    passages.extend(_constraint_passages(finding))
    section = reference_section(model, finding.location)
    if section is not None:
        passages.append(
            Passage(
                source=section.source,
                label=section.label,
                text=section.text,
                why="the JSON reference entry for the element at this location",
            )
        )
    datatype = _DATATYPE.match(finding.rule.citation)
    if datatype is not None:
        name = datatype.group(1).removesuffix("Datatype").lower()
        passages.extend(_sections_matching("metaschema-datatypes", name, limit=2))
    if finding.rule.url == SCHEMA_URL:
        passages.extend(_keyword_passages(finding.rule.citation, ["validation"], limit=1))
    concept = CONCEPT_FOR_MODEL.get(model)
    pool = [c for c in (concept, "uri-use", "identifier-use", "layer-overview") if c]
    passages.extend(_keyword_passages(finding.message + " " + finding.code, pool, limit=2))
    return _budget(passages, each=6000, total=24000)


def passages_for_question(question: str, model: str | None = None) -> list[Passage]:
    """Evidence for a free-text question: named constraints first, then by keyword."""
    passages: list[Passage] = []
    for identifier in re.findall(r"\b(oscal-[\w-]+)\b", question):
        for module_path in sorted(VENDOR_DIR.glob("*_metaschema_RESOLVED.xml")):
            snippet = constraint_snippet(identifier, module_path.name)
            if snippet is not None:
                passages.append(
                    Passage(
                        source=f"vendor:{module_path.name}",
                        label=identifier,
                        text=snippet,
                        why="the constraint as NIST declared it",
                    )
                )
    for kind in ("is-unique", "index-has-key", "has-cardinality", "allowed-values", "index"):
        if kind in question:
            passages.extend(_sections_matching("metaschema-constraints", kind, limit=1))
    pool = [
        identifier
        for identifier in manifest()
        if not identifier.startswith("reference-")
        or (model is not None and identifier == REFERENCE_FOR_MODEL.get(model))
    ]
    passages.extend(_keyword_passages(question, pool, limit=6))
    return _budget(passages, each=6000, total=24000)
