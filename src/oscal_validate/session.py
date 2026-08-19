"""What one validation run has in front of it.

A run is the primary document, whatever documents were supplied to resolve
against, the vendored JSON Schema, and the vendored constraint layer. Bundling
them means a check never has to reach for a global, and it makes the one thing
that changes a finding's severity -- whether the effective data model is
complete -- explicit at every use.
"""

from __future__ import annotations

from dataclasses import dataclass

from .corpus import Corpus, ImportEdge
from .metaschema import Metaschema
from .schema import SchemaIndex


@dataclass(frozen=True)
class Session:
    corpus: Corpus
    schema: SchemaIndex
    metaschema: Metaschema

    @property
    def complete(self) -> bool:
        """True when every document the primary imports was supplied."""
        return self.corpus.complete

    @property
    def incompleteness(self) -> str:
        """A phrase naming why the effective data model is short, for a message.

        An import can fail to resolve for two different reasons, and a caller
        acts on them differently. Nothing was supplied for it, in which case
        the fix is to supply it. Or more than one distinct supplied document
        answers to its file name, in which case it *was* supplied and the fix
        is to narrow ``--resolve`` to the one that is meant. Both leave the
        effective data model incomplete; only the first is a missing document,
        and describing the second as one sends the reader to do again what
        they have already done.
        """
        clauses = [
            phrase
            for phrase in (
                _absent_phrase(self.corpus.absent_imports),
                _ambiguous_phrase(self.corpus.ambiguous_imports),
            )
            if phrase
        ]
        if not clauses:
            return ""
        return f"{', and '.join(clauses)}, so the effective data model is incomplete"

    @property
    def remedy(self) -> str:
        """The sentence telling the reader what to do about ``incompleteness``.

        It has to follow from the same facts the phrase above is built on. The
        two reasons take opposite actions -- supply a document, or supply
        fewer -- so a single fixed sentence was wrong for one of them, and it
        was the ambiguous case it was wrong for.
        """
        absent = bool(self.corpus.absent_imports)
        ambiguous = bool(self.corpus.ambiguous_imports)
        if absent and ambiguous:
            return (
                "Supply the missing document with --resolve, and narrow --resolve to the "
                "one file each ambiguous import means, to settle this."
            )
        if ambiguous:
            return (
                "Narrow --resolve to the one file this import means, rather than a "
                "directory holding more than one document of that name, to settle this."
            )
        return "Supply the imported document with --resolve to settle this."


def _listed(edges: tuple[ImportEdge, ...]) -> str:
    hrefs = sorted({edge.href for edge in edges})
    more = "" if len(hrefs) <= 4 else f", and {len(hrefs) - 4} more"
    return f"{', '.join(hrefs[:4])}{more}"


def _absent_phrase(edges: tuple[ImportEdge, ...]) -> str:
    if not edges:
        return ""
    return (
        f"{len(edges)} imported document(s) named by this document were not supplied "
        f"({_listed(edges)})"
    )


def _ambiguous_phrase(edges: tuple[ImportEdge, ...]) -> str:
    if not edges:
        return ""
    return (
        f"{len(edges)} imported document(s) named by this document each matched more than "
        f"one supplied file ({_listed(edges)}), which leaves which file is meant undetermined"
    )
