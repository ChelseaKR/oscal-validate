"""Choosing which published passages a model is shown, and how much of them.

The sources themselves -- loading them, splitting them into sections, quoting
them verbatim, and hashing the bytes that were read -- live in
:mod:`oscal_validate.sources`, outside this package, because
``oscal-validate rule`` prints the same evidence with no model in the process.
This module is the part that is only about a prompt: which sections answer one
finding or one question, in what order, and inside what byte budget.

Everything the old module exported is re-exported here, so a caller that
imported it from ``oscal_validate.ai.sources`` still works and
``tests/test_ai_sources.py`` still reaches it under that name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..findings import Finding
from ..rules import SCHEMA_URL
from ..sources import (
    CONCEPT_FOR_MODEL,
    CORPUS_DIR,
    MIN_QUOTE_CHARS,
    REFERENCE_FOR_MODEL,
    SOURCE_FOR_URL,
    VENDOR_DIR,
    VENDOR_RELEASE_URL,
    VENDOR_RETRIEVED,
    Section,
    Source,
    constraint_snippet,
    contains,
    load,
    locate,
    manifest,
    normalize,
    reference_section,
    sections,
    source_ids,
)

__all__ = [
    "CONCEPT_FOR_MODEL",
    "CORPUS_DIR",
    "MIN_QUOTE_CHARS",
    "REFERENCE_FOR_MODEL",
    "SOURCE_FOR_URL",
    "VENDOR_DIR",
    "VENDOR_RELEASE_URL",
    "VENDOR_RETRIEVED",
    "Passage",
    "Section",
    "Source",
    "constraint_snippet",
    "contains",
    "load",
    "locate",
    "manifest",
    "normalize",
    "passages_for_finding",
    "passages_for_question",
    "reference_section",
    "sections",
    "source_ids",
]


@dataclass(frozen=True)
class Passage:
    """One piece of evidence shown to the model, with the id it must cite."""

    source: str
    label: str
    text: str
    why: str


_CONSTRAINT_ID = re.compile(r"NIST OSCAL constraint (\S+) \(")
_MODULE = re.compile(r"in (oscal_[\w-]+_metaschema_RESOLVED\.xml)")
_DATATYPE = re.compile(r"^(\w+Datatype) in the vendored")


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
