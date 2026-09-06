"""Near-miss identifiers for a reference that resolved to nothing (issue #64).

The 2026-08-15 imports survey measured 178 real unresolved references and found
the largest class of them one zero-pad away from resolving: an SSP naming
``ac-2_odp.01`` against a baseline that declares ``ac-02_odp.01``. The report
said the reference resolved to nothing and stopped, which is true and is not
the sentence that fixes the file.

Nothing here is invented and no model is involved. Candidates come from the
identifier index the resolution check already built, for the same reference
kind, and the ranking key is fixed:

1. **Normalised equality** — the two strings differ only in ways this module
   names: a leading ``#``, case, the separator character, or zero-padding.
2. **A bounded edit distance** — optimal string alignment (Damerau-Levenshtein
   restricted to adjacent transpositions) of at most :data:`MAX_DISTANCE`.
3. **Lexical order**, so a tie between two equally close identifiers is broken
   by the identifier rather than by dictionary insertion order.

Anything further away is not offered at all: a suggestion a reader has to
evaluate is worth less than no suggestion, and an unbounded "closest" match
always returns something, which is the shape of a number that cannot be wrong.

This stays a suggestion. The finding's code, severity and message are what they
were, and no wording here says the near miss is the intended target -- only
that it is declared, and how it differs from what was written. An UNVERIFIABLE
reference gets nothing, because the index that would be searched is incomplete
by definition and the closest entry in a partial index is not evidence about
anything.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

#: The furthest an identifier may be from the one written and still be offered.
#: Two covers the survey's measured shapes (a dropped zero, a transposition, a
#: separator plus a case change) without reaching identifiers that merely share
#: a prefix.
MAX_DISTANCE = 2

#: The most near misses printed beneath one finding.
MAX_SUGGESTIONS = 3

#: Characters OSCAL identifiers use as separators, folded together so that
#: ``ac-2_odp`` and ``ac-2.odp`` compare equal under the separator rule.
_SEPARATORS = re.compile(r"[-_.]")

#: A run of digits, so ``ac-02`` and ``ac-2`` compare equal under zero-padding.
_DIGITS = re.compile(r"0*(\d)")


def _unify_separators(value: str) -> str:
    return _SEPARATORS.sub("-", value)


def _strip_zero_padding(value: str) -> str:
    return _DIGITS.sub(r"\1", value)


#: The differences this module can name, in the order it names them. Each entry
#: is a normalisation; two identifiers are "normalised-equal" when applying all
#: of them makes the strings identical, and the difference reported is the
#: subset that was actually load-bearing.
_NORMALISERS: tuple[tuple[str, Callable[[str], str]], ...] = (
    ("a leading '#'", lambda value: value.removeprefix("#")),
    ("case", str.casefold),
    ("the separator", _unify_separators),
    ("zero-padding", _strip_zero_padding),
)


@dataclass(frozen=True)
class Suggestion:
    """One declared identifier close to one that resolved to nothing.

    ``difference`` says what a reader has to change, in this module's own
    vocabulary; it never asserts that ``value`` is what was meant.
    """

    value: str
    difference: str

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value, "difference": self.difference}

    def render_text(self) -> str:
        return f"    also declared: {self.value}  (differs by {self.difference})"


def _apply(normalisers: Iterable[Callable[[str], str]], value: str) -> str:
    for normalise in normalisers:
        value = normalise(value)
    return value


def _normalised_difference(written: str, declared: str) -> str | None:
    """How ``declared`` differs from ``written``, or ``None`` if not this close.

    Only the normalisations that are *needed* are named: dropping one and
    finding the two strings no longer equal is what makes it load-bearing.
    Where no single normalisation is individually necessary -- two of them
    happen to repair the same difference -- every normalisation that changes
    either string is named instead, so the answer is never empty when the
    strings genuinely differ.
    """
    everything = [normalise for _, normalise in _NORMALISERS]
    if _apply(everything, written) != _apply(everything, declared):
        return None
    needed = [
        name
        for index, (name, _) in enumerate(_NORMALISERS)
        if _apply(
            [n for position, (_, n) in enumerate(_NORMALISERS) if position != index],
            written,
        )
        != _apply(
            [n for position, (_, n) in enumerate(_NORMALISERS) if position != index],
            declared,
        )
    ]
    if not needed:
        needed = [
            name
            for name, normalise in _NORMALISERS
            if normalise(written) != written or normalise(declared) != declared
        ]
    if not needed:
        return None
    return " and ".join(needed)


def distance(written: str, declared: str, cap: int = MAX_DISTANCE) -> int | None:
    """Optimal string alignment distance, or ``None`` once it exceeds ``cap``.

    Damerau-Levenshtein restricted to adjacent transpositions, which is what
    the survey's shapes need: a swapped pair of characters is one edit, not
    two. The length gate short-circuits the common case, and the row minimum
    abandons a row that can no longer come in under the cap, so a large
    identifier index does not cost a full matrix per candidate.
    """
    if written == declared:
        return 0
    if abs(len(written) - len(declared)) > cap:
        return None
    previous = list(range(len(declared) + 1))
    before_previous: list[int] = []
    for i, source in enumerate(written, start=1):
        current = [i] + [0] * len(declared)
        for j, target in enumerate(declared, start=1):
            cost = 0 if source == target else 1
            current[j] = min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + cost,
            )
            if (
                i > 1
                and j > 1
                and source == declared[j - 2]
                and written[i - 2] == target
                and before_previous
            ):
                current[j] = min(current[j], before_previous[j - 2] + 1)
        if min(current) > cap:
            return None
        before_previous, previous = previous, current
    return previous[-1] if previous[-1] <= cap else None


def near_misses(
    written: str,
    declared: Iterable[str],
    *,
    prefix: str = "",
    limit: int = MAX_SUGGESTIONS,
) -> tuple[Suggestion, ...]:
    """The identifiers closest to ``written``, ranked by the documented key.

    ``prefix`` is prepended to every suggested value so that a bare fragment
    suggested for a ``#``-prefixed href comes back as a drop-in replacement for
    what was written, rather than as a string the reader has to re-decorate.
    """
    scored: list[tuple[int, int, str, str]] = []
    for candidate in declared:
        if candidate == written:
            continue
        difference = _normalised_difference(written, candidate)
        if difference is not None:
            # Every normalised-equal candidate is the same distance away for
            # ranking purposes -- none of them requires reading the identifier
            # differently -- so lexical order alone separates them.
            scored.append((0, 0, candidate, difference))
            continue
        edits = distance(written, candidate)
        if edits is not None:
            scored.append(
                (1, edits, candidate, f"{edits} character edit" + ("s" if edits != 1 else ""))
            )
    scored.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
    return tuple(
        Suggestion(value=f"{prefix}{value}", difference=difference)
        for _, _, value, difference in scored[:limit]
    )


__all__ = [
    "MAX_DISTANCE",
    "MAX_SUGGESTIONS",
    "Suggestion",
    "distance",
    "near_misses",
]
