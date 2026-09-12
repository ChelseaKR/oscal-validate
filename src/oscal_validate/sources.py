"""The published text this tool quotes, with the hash of the bytes it read.

Two kinds of source live here. The corpus holds text extracted from NIST's
pages by ``tools/corpus_fetch.py``, each with its URL, retrieval date, and
hashes in ``MANIFEST.json``. The vendored schema and metaschema files under
``vendor/`` are sources too, under ids of the form ``vendor:<file>``, with the
hashes ``vendor/SOURCES.md`` already enforces.

On top of the raw text sit sections -- each corpus page split at its headings,
where a reference page's nested headings are the JSON names of the model, so a
finding's location pointer maps to the section describing that element -- and
``contains``, which says whether a quote occurs verbatim in a named source
after one normalization (whitespace collapsed, typographic quotes
straightened) applied to both sides.

This module used to be ``ai/sources.py`` in its entirety. It moved out because
the evidence is not only for the model: ``oscal-validate rule`` prints the same
declaration, the same specification passage and the same hashes with no model
and no SDK, and ``ai/sources.py`` now imports this and adds only the part that
is about a prompt -- choosing passages and keeping them inside a byte budget.
Two commands quoting one source layer cannot drift from each other.

The corpus **files** did not move. ``ai/corpus/`` is where ADR-0005, the data
card in ``docs/data/nist-documentation-corpus.md``, ``pyproject.toml``'s
package-data and the CHANGELOG all say the text lives, and relocating package
data to make an import graph read better would falsify four documents to tidy
one. The directory is data, not code: this module imports nothing from the
model-backed package, and ``tests/test_offline_guarantee.py`` still holds that
boundary.

Every ``Source`` carries the SHA-256 of the text this process actually read,
computed rather than copied out of the manifest, for the reason
``snapshot.py`` gives: a recorded hash answers "what did we write down", and a
computed one answers "what did this run quote".
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from .rules import IDENTIFIER_USE_URL, URI_USE_URL

CORPUS_DIR = Path(__file__).resolve().parent / "ai" / "corpus"
VENDOR_DIR = Path(__file__).resolve().parent / "vendor" / "oscal"
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

#: The corpus page holding the Metaschema specification, whose "Constraint
#: Types" subsections are one per constraint kind.
SPECIFICATION = "metaschema-constraints"


def specification_path(kind: str) -> tuple[str, ...]:
    """The heading path of the specification section describing one kind.

    Built from the kind rather than looked up, because the page names its
    subsections uniformly. ``tests/test_rule_verb.py`` checks that every kind
    NIST publishes resolves to a real section, so a page that stopped
    following the pattern fails rather than silently printing nothing.
    """
    return ("Constraints", "Constraint Types", f"{kind} Constraints")


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

    @property
    def digest(self) -> str:
        """SHA-256 of the text as read, so a quotation can name its bytes."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Section:
    source: str
    path: tuple[str, ...]
    heading: str
    text: str

    @property
    def label(self) -> str:
        return "/".join(self.path) if self.path else self.heading


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


def section_at(identifier: str, path: tuple[str, ...]) -> Section | None:
    """One section by its exact heading path, or None. Never a near match."""
    return next((s for s in sections(identifier) if s.path == path), None)


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

CONSTRAINT_KINDS = (
    "is-unique",
    "index",
    "index-has-key",
    "has-cardinality",
    "matches",
    "expect",
    "allowed-values",
)


def constraint_snippet(identifier: str, module: str) -> str | None:
    """The XML element declaring one constraint, verbatim from the vendored file."""
    source = load(f"vendor:{module}")
    if source is None:
        return None
    match = re.search(
        rf"<({'|'.join(CONSTRAINT_KINDS)})"
        rf"\b[^>]*\bid=\"{re.escape(identifier)}\"[^>]*(?:/>|>.*?</\1>)",
        source.text,
        re.DOTALL,
    )
    return match.group(0) if match else None


__all__ = [
    "CONCEPT_FOR_MODEL",
    "CONSTRAINT_KINDS",
    "CORPUS_DIR",
    "MIN_QUOTE_CHARS",
    "REFERENCE_FOR_MODEL",
    "SOURCE_FOR_URL",
    "SPECIFICATION",
    "VENDOR_DIR",
    "VENDOR_RELEASE_URL",
    "VENDOR_RETRIEVED",
    "Section",
    "Source",
    "constraint_snippet",
    "contains",
    "load",
    "locate",
    "manifest",
    "normalize",
    "reference_section",
    "section_at",
    "sections",
    "source_ids",
    "specification_path",
]
