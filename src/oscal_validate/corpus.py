"""The effective data model: the document, plus whatever was supplied with it.

NIST defines what a reference in an OSCAL document is allowed to reach:

    "The effective data model of a document includes all objects identified
    with the document and any directly or transitively imported documents."
    -- NIST, "URI Usage", Linking to another OSCAL object

That sentence is the whole of this module's job, and it is also the reason this
tool can say anything definite about a reference at all. A catalog that imports
nothing has an effective data model equal to itself, so a reference in it that
resolves nowhere is *wrong*. A profile that imports a catalog has an effective
data model this tool cannot see unless the catalog is handed to it, so the same
unresolved reference is *unknown*. The two are reported differently, always.

Imports are matched to supplied files by file name, never fetched. Which
imports were matched and which were not is reported in the output, so an
UNVERIFIABLE finding is always accompanied by the reason it could not be
settled.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .document import DocumentError, Scalar, Walked, walk_document
from .schema import SchemaIndex

#: Pointer segments under which an ``href`` names another OSCAL document.
#: Read off the model roots in the vendored schema; pinned by
#: ``tests/test_corpus.py::test_import_segments_exist_in_the_vendored_schema``.
IMPORT_SEGMENTS = frozenset(
    {
        "imports",
        "import-profile",
        "import-ssp",
        "import-ap",
        "import-component-definitions",
    }
)

#: A component definition points at the catalog or profile it implements
#: through ``control-implementation/source`` rather than an import assembly.
IMPORT_SCALAR_NAMES = frozenset({"source"})


@dataclass(frozen=True)
class LoadedDocument:
    path: str
    name: str
    walked: Walked


@dataclass(frozen=True)
class ImportEdge:
    """One pointer from a document to another document."""

    pointer: str
    href: str
    #: The file name the href resolves to, or None when the href is a bare
    #: fragment this tool could not turn into a file name.
    target_name: str | None
    resolved_to: str | None

    @property
    def resolved(self) -> bool:
        return self.resolved_to is not None


@dataclass
class Corpus:
    """Every document supplied, and how completely they compose."""

    primary: LoadedDocument
    supporting: tuple[LoadedDocument, ...] = ()
    edges: tuple[ImportEdge, ...] = ()
    #: Documents reachable from the primary through resolved imports.
    reachable: tuple[LoadedDocument, ...] = ()

    @property
    def complete(self) -> bool:
        """True when every import in the reachable set was supplied."""
        return all(edge.resolved for edge in self.edges)

    @property
    def unresolved_imports(self) -> tuple[ImportEdge, ...]:
        return tuple(edge for edge in self.edges if not edge.resolved)

    def scalars(self) -> list[Scalar]:
        out: list[Scalar] = []
        for document in self.reachable:
            out.extend(document.walked.scalars)
        return out


def load_document(path: Path, schema: SchemaIndex) -> LoadedDocument:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocumentError(f"cannot read {path}: {exc}") from exc
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DocumentError(f"{path} is not valid JSON: {exc}") from exc
    return LoadedDocument(path=str(path), name=path.name, walked=walk_document(data, schema))


def collect_paths(paths: list[Path]) -> list[Path]:
    """Expand directories into the ``.json`` files directly inside them."""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(p for p in path.iterdir() if p.suffix == ".json"))
        else:
            found.append(path)
    return found


def import_edges(document: LoadedDocument) -> list[tuple[str, str]]:
    """(pointer, href) for every reference this document makes to another document."""
    edges: list[tuple[str, str]] = []
    for scalar in document.walked.scalars:
        if not isinstance(scalar.value, str):
            continue
        segments = scalar.pointer.split("/")
        is_import_href = scalar.name == "href" and any(s in IMPORT_SEGMENTS for s in segments)
        if is_import_href or scalar.name in IMPORT_SCALAR_NAMES:
            edges.append((scalar.pointer, scalar.value))
    return edges


MARKER = "/back-matter/resources/"


def back_matter_rlinks(document: LoadedDocument) -> dict[str, list[str]]:
    """Back-matter resource UUID -> the hrefs its rlinks point at.

    A profile that imports ``#<uuid>`` is naming a back-matter resource in its
    own document; the file it actually wants is on that resource's rlinks.
    """
    uuids: dict[str, str] = {}
    hrefs: dict[str, list[str]] = {}
    for scalar in document.walked.scalars:
        if MARKER not in scalar.pointer or not isinstance(scalar.value, str):
            continue
        index = scalar.pointer.split(MARKER, 1)[1].split("/")[0]
        if scalar.pointer.endswith(f"{MARKER}{index}/uuid"):
            uuids[index] = scalar.value
        elif scalar.name == "href":
            hrefs.setdefault(index, []).append(scalar.value)
    return {uuid: hrefs.get(index, []) for index, uuid in uuids.items()}


def file_name_of(href: str, rlinks: dict[str, list[str]]) -> str | None:
    """The file name an href names, following a back-matter resource if needed."""
    split = urlsplit(href)
    if not split.path and split.fragment:
        for candidate in rlinks.get(split.fragment, []):
            name = file_name_of(candidate, {})
            if name is not None:
                return name
        return None
    tail = split.path.rsplit("/", 1)[-1]
    return tail or None


def _match(
    name: str | None,
    by_name: dict[str, list[LoadedDocument]],
    by_stem: dict[str, list[LoadedDocument]],
) -> list[LoadedDocument]:
    """Find the supplied document an href names.

    Exact file name first. Failing that, the file name without its extension:
    OSCAL is published in XML, JSON, and YAML side by side under one stem, and
    a JSON profile in the wild routinely imports the XML serialization of its
    catalog. Matching on the stem is a stated convenience of this tool, not a
    rule from the specification, and it is why the report always names which
    file an import was matched to.
    """
    if name is None:
        return []
    exact = by_name.get(name, [])
    if exact:
        return exact
    return by_stem.get(Path(name).stem, [])


def _where(document: LoadedDocument, primary: LoadedDocument, pointer: str) -> str:
    """A pointer, qualified by file name when it is not in the primary document."""
    return pointer if document is primary else f"{document.path}#{pointer}"


def build_corpus(primary: Path, supporting_paths: list[Path], schema: SchemaIndex) -> Corpus:
    """Load the primary document and every document supplied to resolve against."""
    primary_document = load_document(primary, schema)
    supporting = tuple(
        load_document(path, schema)
        for path in collect_paths(supporting_paths)
        if path.resolve() != primary.resolve()
    )
    by_name: dict[str, list[LoadedDocument]] = {}
    by_stem: dict[str, list[LoadedDocument]] = {}
    for document in supporting:
        by_name.setdefault(document.name, []).append(document)
        by_stem.setdefault(Path(document.name).stem, []).append(document)

    edges: list[ImportEdge] = []
    reachable: list[LoadedDocument] = [primary_document]
    seen: set[str] = {primary_document.path}
    queue: list[LoadedDocument] = [primary_document]
    while queue:
        document = queue.pop(0)
        rlinks = back_matter_rlinks(document)
        for pointer, href in import_edges(document):
            name = file_name_of(href, rlinks)
            matches = _match(name, by_name, by_stem)
            target = matches[0] if len(matches) == 1 else None
            edges.append(
                ImportEdge(
                    pointer=pointer
                    if document is primary_document
                    else f"{document.path}#{pointer}",
                    href=href,
                    target_name=name,
                    resolved_to=target.path if target is not None else None,
                )
            )
            if target is not None and target.path not in seen:
                seen.add(target.path)
                reachable.append(target)
                queue.append(target)

    return Corpus(
        primary=primary_document,
        supporting=supporting,
        edges=tuple(edges),
        reachable=tuple(reachable),
    )


__all__ = [
    "IMPORT_SCALAR_NAMES",
    "IMPORT_SEGMENTS",
    "Corpus",
    "ImportEdge",
    "LoadedDocument",
    "back_matter_rlinks",
    "build_corpus",
    "collect_paths",
    "file_name_of",
    "import_edges",
    "load_document",
]
