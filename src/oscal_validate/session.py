"""What one validation run has in front of it.

A run is the primary document, whatever documents were supplied to resolve
against, the vendored JSON Schema, and the vendored constraint layer. Bundling
them means a check never has to reach for a global, and it makes the one thing
that changes a finding's severity -- whether the effective data model is
complete -- explicit at every use.
"""

from __future__ import annotations

from dataclasses import dataclass

from .corpus import Corpus
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
        """A phrase naming what is missing, for a finding's message."""
        missing = self.corpus.unresolved_imports
        if not missing:
            return ""
        listed = ", ".join(sorted({edge.href for edge in missing})[:4])
        more = "" if len(missing) <= 4 else f", and {len(missing) - 4} more"
        return (
            f"{len(missing)} imported document(s) named by this document were not supplied "
            f"({listed}{more}), so the effective data model is incomplete"
        )
