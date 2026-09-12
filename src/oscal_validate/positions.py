"""Where in the source bytes a JSON Pointer points, for the run that asks.

A finding's location is an RFC 6901 JSON Pointer. That is exact, it is what
``Finding.sort_key`` orders on, what ``--baseline`` keys on, what ``diff``
compares and what ``tests/golden/`` holds — and it is not where a person's
editor is. This module maps a pointer back to the line and column of the value
it names, so a finding can be reported at a physical position *beside* its
pointer and never in place of it.

Three rules decide what this module is allowed to say.

**A position is computed only when it is asked for.** Indexing means a second
pass over the source text of every document the run read, and the default
path's cost is a promise this tool keeps. ``--locations`` is what asks; without
it no index is built and no finding carries a position.

**A pointer with no recorded position reports nothing, never zero.** Line 0 and
column 0 do not exist. A finding whose pointer names a value that is not in the
source — one the walk synthesised, or one in a document whose bytes this run
did not index — carries no position at all, and both renderings say so in
words. Publishing ``0`` there would be a fabricated measurement of exactly the
kind this tool exists to refuse.

**The index has to agree with ``json.loads`` about what the document says, and
where it could disagree it defers.** String escaping goes through
``json.decoder.scanstring``, the same function the standard library's own
decoder uses, so a pointer token containing an escape is spelled identically.
A duplicate key records the *last* position, because the last value is the one
``json.loads`` keeps: recording the first would point a reader at a value the
rest of the report is not about.

The scan is a reader over the source text rather than a hook into ``json``'s
scanner. The hook is private API and the C scanner does not expose offsets at
all; the reader is a stated, testable grammar. It is written with an explicit
stack rather than recursion so that a deeply nested document cannot exhaust the
interpreter's stack in a code path the document walk has not reached yet.
"""

from __future__ import annotations

import json.decoder
import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from .document import escape

if TYPE_CHECKING:  # pragma: no cover - imported for types only
    # ``findings`` imports ``Position`` from this module and ``corpus`` imports
    # ``SourceIndex``, so importing either of them here at run time would close
    # a cycle. Nothing below needs them at run time: ``attach`` reads
    # attributes off the objects it is handed.
    from .corpus import Corpus, LoadedDocument
    from .findings import Finding

#: The standard library's own string reader: given the source and the offset
#: just past an opening quote, it returns the decoded string and the offset
#: just past the closing quote. Using it rather than a second implementation is
#: what makes a pointer token containing an escape spell the same here as it
#: does after ``json.loads``. It is not in ``__all__`` and typeshed does not
#: declare it, so the binding is typed here rather than inferred.
_scanstring: Callable[[str, int], tuple[str, int]] = json.decoder.scanstring  # type: ignore[attr-defined]

#: Runs of JSON whitespace. Compiled rather than a character loop because
#: ``--locations`` is asked of real OSCAL catalogs, and the largest in this
#: project's own corpus is 26 MB.
_WHITESPACE = re.compile(r"[ \t\n\r]*")

#: Everything that can follow a bare literal — a number, ``true``, ``false``,
#: ``null``, and the ``NaN``/``Infinity`` extensions ``json.loads`` accepts by
#: default. The text has already been through ``json.loads`` by the time it
#: reaches here, so this only has to find where the literal ends.
_LITERAL_END = re.compile(r"[,\]}\s]")


class PositionError(ValueError):
    """The source text is not the JSON this index was told it would be.

    Raised only where the reader and ``json.loads`` disagree, which cannot
    happen for a document that was decoded successfully before the index was
    built. It exists so that a disagreement is loud rather than silently
    yielding an index with a hole in it.
    """


@dataclass(frozen=True)
class Position:
    """Where a value begins in the source: the file, and a 1-based line and column.

    ``line`` and ``column`` count from 1, the way every editor and every
    problem matcher does. ``column`` counts characters, so a line with an
    astral-plane character in it is counted in code points and not in UTF-8
    bytes; ``docs/API.md`` says so, because the two differ and a consumer that
    assumes bytes would be off by the difference.
    """

    file: str
    line: int
    column: int

    def render(self) -> str:
        return f"{self.file}:{self.line}:{self.column}"


class SourceIndex:
    """Every JSON Pointer in one document, and where its value starts.

    Offsets are held rather than line/column pairs: an offset is one integer
    per pointer, and a 26 MB catalog has a few hundred thousand of them.
    """

    def __init__(self, path: str, text: str) -> None:
        self.path = path
        self._offsets = _scan(text)
        self._line_starts = _line_starts(text)

    def __len__(self) -> int:
        return len(self._offsets)

    def position(self, pointer: str) -> Position | None:
        """Where ``pointer``'s value begins, or None when it names nothing here."""
        offset = self._offsets.get(pointer)
        if offset is None:
            return None
        line = bisect_right(self._line_starts, offset)
        return Position(
            file=self.path,
            line=line,
            column=offset - self._line_starts[line - 1] + 1,
        )


def _line_starts(text: str) -> list[int]:
    starts = [0]
    start = text.find("\n")
    while start != -1:
        starts.append(start + 1)
        start = text.find("\n", start + 1)
    return starts


def _skip(text: str, index: int) -> int:
    match = _WHITESPACE.match(text, index)
    return match.end() if match is not None else index


def _at(text: str, index: int) -> str:
    return text[index] if index < len(text) else ""


def _member_name(text: str, index: int) -> tuple[str, int]:
    """The key at ``index`` and the offset just past its colon."""
    if _at(text, index) != '"':
        raise PositionError(f"expected a member name at offset {index}")
    key, end = _scanstring(text, index + 1)
    end = _skip(text, end)
    if _at(text, end) != ":":
        raise PositionError(f"expected ':' after a member name at offset {end}")
    return key, end + 1


def _literal_end(text: str, index: int) -> int:
    """The offset just past the scalar that begins at ``index``."""
    if text[index] == '"':
        _, end = _scanstring(text, index + 1)
        return end
    match = _LITERAL_END.search(text, index)
    end = match.start() if match is not None else len(text)
    if end == index:
        raise PositionError(f"expected a value at offset {index}")
    return end


#: One open container: whether it is an object or an array, the pointer of the
#: container itself, and — for an array — the index of the element being read.
_Frame = tuple[str, str, list[int]]


def _read_value(
    text: str, index: int, pointer: str, offsets: dict[str, int], stack: list[_Frame]
) -> tuple[int, str, bool]:
    """Record where the value at ``pointer`` begins, and read past it.

    Returns the new offset, the pointer to read next, and whether the reader
    descended into a container. Descending means the caller has a value to
    read; not descending means a value has just been finished and the caller
    has to climb.
    """
    if index >= len(text):
        raise PositionError("the document ends where a value was expected")
    offsets[pointer] = index
    character = text[index]
    if character == "{":
        index = _skip(text, index + 1)
        if _at(text, index) == "}":
            return index + 1, pointer, False
        stack.append(("object", pointer, []))
        name, index = _member_name(text, index)
        return _skip(text, index), f"{pointer}/{escape(name)}", True
    if character == "[":
        index = _skip(text, index + 1)
        if _at(text, index) == "]":
            return index + 1, pointer, False
        stack.append(("array", pointer, [0]))
        return index, f"{pointer}/0", True
    return _literal_end(text, index), pointer, False


def _ascend(text: str, index: int, pointer: str, stack: list[_Frame]) -> tuple[int, str, bool]:
    """Climb out of every container the last value closed, to the next sibling.

    Returns the new offset, the pointer of that sibling, and whether there is
    one. False means every container is closed and the document is read.
    """
    while stack:
        kind, prefix, counter = stack[-1]
        index = _skip(text, index)
        character = _at(text, index)
        if character == ",":
            index = _skip(text, index + 1)
            if kind == "object":
                name, index = _member_name(text, index)
                return _skip(text, index), f"{prefix}/{escape(name)}", True
            counter[0] += 1
            return index, f"{prefix}/{counter[0]}", True
        if character == ("}" if kind == "object" else "]"):
            index += 1
            stack.pop()
            pointer = prefix
            continue
        raise PositionError(
            f"expected ',' or a closing bracket at offset {index}, found {character!r}"
        )
    return index, pointer, False


def _scan(text: str) -> dict[str, int]:
    """Pointer -> the offset where that pointer's value begins.

    One pass, with an explicit stack of the containers currently open rather
    than recursion, so that a document nested deeper than the interpreter's
    stack cannot fail here in a code path the document walk has not reached.
    """
    offsets: dict[str, int] = {}
    stack: list[_Frame] = []
    pointer = ""
    index = _skip(text, 0)
    while True:
        index, pointer, descended = _read_value(text, index, pointer, offsets, stack)
        if descended:
            continue
        index, pointer, sibling = _ascend(text, index, pointer, stack)
        if not sibling:
            break
    if _skip(text, index) != len(text):
        raise PositionError(f"trailing content after the document at offset {index}")
    return offsets


def index_document(path: str, text: str) -> SourceIndex:
    """Index one document's source text. See :class:`SourceIndex`."""
    return SourceIndex(path, text)


def _split(location: str, documents: tuple[LoadedDocument, ...]) -> tuple[str | None, str]:
    """Which document a finding's location is in, and the pointer inside it.

    ``build_corpus`` writes a finding in a supplied document as
    ``<path>#<pointer>`` and one in the primary document as the bare pointer.
    A path is matched by exact prefix against the documents this run actually
    read, never by splitting on the first ``#``: a JSON Pointer token may
    contain a ``#``, and a guess here would attach a position from the wrong
    file.

    **The known paths are tried first, and the order is the whole function.**
    A bare pointer begins with ``/`` -- and so does an absolute path, which is
    what a document supplied as ``--resolve /some/where/catalog.json`` is
    written as. Testing for ``/`` first therefore read every finding in every
    absolutely-pathed supporting document as a pointer into the primary
    document, found nothing there, and reported no position at all. Measured
    on a two-level profile chain in a temporary directory: one finding of
    seven, and it was silent.
    """
    for document in documents:
        prefix = f"{document.path}#"
        if location.startswith(prefix):
            return document.path, location[len(prefix) :]
    if location.startswith("/"):
        return None, location
    return None, ""


def attach(findings: list[Finding], corpus: Corpus) -> list[Finding]:
    """Give every finding the source position its pointer names, where there is one.

    A no-op when the run built no index, which is every run without
    ``--locations``. Called after ``finalize`` so that deduplication and
    ordering are decided on exactly the fields they were decided on before this
    existed, and again after ``--baseline`` is applied, because a
    ``BASELINE_STALE`` finding is made after ``validate`` has returned and
    would otherwise be the one finding in a report with no position for a
    reason that has nothing to do with the document.
    """
    by_path = {
        document.path: document.source
        for document in corpus.reachable
        if document.source is not None
    }
    if not by_path:
        return findings
    primary = corpus.primary.source
    attached: list[Finding] = []
    for finding in findings:
        path, pointer = _split(finding.location, corpus.reachable)
        index = primary if path is None else by_path.get(path)
        position = index.position(pointer) if index is not None and pointer else None
        attached.append(finding if position is None else replace(finding, position=position))
    return attached


__all__ = [
    "Position",
    "PositionError",
    "SourceIndex",
    "attach",
    "index_document",
]
