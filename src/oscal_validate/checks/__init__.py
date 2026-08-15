"""The check registry, in the order the README documents them."""

from __future__ import annotations

from collections.abc import Callable

from ..findings import Finding
from ..session import Session
from . import (
    constraints,
    datatypes,
    identifiers,
    imports,
    references,
    structure,
    versions,
)

Check = Callable[[Session], list[Finding]]

ALL_CHECKS: tuple[Check, ...] = (
    imports.check,
    structure.check,
    datatypes.check,
    constraints.check,
    identifiers.check,
    references.check,
    versions.check,
)

__all__ = ["ALL_CHECKS", "Check"]
