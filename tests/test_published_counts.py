"""Every coverage number the living prose states is measured off the vendored files.

`docs/CONSTRAINT-COVERAGE.md` is generated and `tests/test_constraint_coverage.py`
fails when it goes stale, so the table cannot drift. The prose around it could,
and did: the count went 78 to 102 to 113 across two expansions, and each move
left a sentence behind. On 2026-09-05 the README still said "the 102
constraints this tool evaluates" one section above "It evaluates 113 of NIST's
340 published constraints", and `docs/RESPONSIBLE-TECH-AUDITS.md` still said 78
in the sentence that sizes the harm the whole audit is about. Both numbers were
correct when written and neither was checked by anything.

So this test reads the numbers back out of the prose and holds each one against
the same parse the validator runs. A count that moves now fails here until the
sentences move with it, which is the difference between a number that is
published and a number that is maintained.

**Which documents are in scope.** Only the ones that speak in the present
tense about what the tool does today:

- `README.md` — the front door.
- `docs/RESPONSIBLE-TECH-AUDITS.md` — a living artifact, "reviewed on release",
  whose risk statement is sized by this number.

Deliberately out of scope: the ADRs, `docs/findings/`, the decided entries in
`docs/ROADMAP.md`, and the phase records in `docs/EXPANSION-PLAN.md`. Those are
dated records of what was true on their date, and 78 or 102 is the right number
in them. Rewriting a dated record to match today would be the more damaging
kind of drift, so nothing here touches them.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from oscal_validate.metaschema import load_metaschema

ROOT = Path(__file__).resolve().parent.parent

#: Documents whose coverage numbers are claims about the present.
LIVE_DOCUMENTS = ("README.md", "docs/RESPONSIBLE-TECH-AUDITS.md")

#: The constraint kinds NIST declares, longest name first so that
#: ``index-has-key`` is never matched as ``index`` followed by stray text.
KINDS = (
    "allowed-values",
    "has-cardinality",
    "index-has-key",
    "is-unique",
    "matches",
    "expect",
    "index",
)

#: Every sentence shape the live documents use to state a count, paired with
#: the name of the measured quantity each captured group must equal. A shape
#: that matches with the wrong number fails; a shape that stops matching is
#: caught by ``test_no_coverage_number_escapes_a_check`` below, so a rewrite
#: cannot quietly remove a claim from the check by rephrasing it.
CLAIMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # "It evaluates 113 of NIST's 340 published constraints."
    (
        r"evaluates\s+(\d+)\s+of\s+(?:NIST's\s+)?(\d+)\s+published\s+constraints",
        ("evaluated", "total"),
    ),
    # "One of the 113 constraints this tool evaluates is an index-has-key ..."
    (r"the\s+(\d+)\s+constraints\s+this\s+tool\s+evaluates", ("evaluated",)),
    # "the 227 published constraints this tool does not evaluate"
    (
        r"the\s+(\d+)\s+published\s+constraints\s+this\s+tool\s+does\s+not\s+evaluate",
        ("unevaluated",),
    ),
    # "Every one of the other 227 is listed with its reason in ..."
    (r"the\s+other\s+(\d+)\s+is\s+listed", ("unevaluated",)),
    # "OSCAL 1.2.3 declares 340 constraints there: ..."
    (r"declares\s+(\d+)\s+constraints", ("total",)),
    # "lists all 340 published constraints with whether each is evaluated"
    (r"all\s+(\d+)\s+published\s+constraints", ("total",)),
    # "of the 200 `allowed-values` sets, 60 declare `allow-other` and 140 do not"
    (
        r"of\s+the\s+(\d+)\s+`allowed-values`\s+sets,\s+(\d+)\s+declare\s+`allow-other`"
        r"\s+and\s+(\d+)\s+do\s+not",
        ("published:allowed-values", "allow-other declared", "allow-other absent"),
    ),
    # "11 of the 25 `matches` constraints are evaluated and the other 14 ..."
    (
        r"(\d+)\s+of\s+the\s+(\d+)\s+`matches`\s+constraints\s+are\s+evaluated\s+and\s+the\s+other\s+(\d+)",
        ("evaluated:matches", "published:matches", "unevaluated:matches"),
    ),
)

#: "48 `is-unique`", "12 `expect`", "200 `allowed-values`": a number immediately
#: in front of a backticked kind is that kind's published total, wherever the
#: sentence around it goes.
PER_KIND = re.compile(r"(\d+)\s+`(" + "|".join(KINDS) + r")`")


def _measured() -> dict[str, int]:
    """Every quantity the prose is allowed to state, taken from the vendored files."""
    metaschema = load_metaschema()
    published = Counter(c.kind for c in metaschema.constraints)
    evaluated = Counter(c.kind for c in metaschema.evaluated())
    allowed = [c for c in metaschema.skipped() if c.kind == "allowed-values"]
    declared_open = [c for c in allowed if c.allow_other == "yes"]

    measured = {
        "total": len(metaschema.constraints),
        "evaluated": len(metaschema.evaluated()),
        "unevaluated": len(metaschema.skipped()),
        "allow-other declared": len(declared_open),
        "allow-other absent": len(allowed) - len(declared_open),
    }
    for kind in KINDS:
        measured[f"published:{kind}"] = published[kind]
        measured[f"evaluated:{kind}"] = evaluated[kind]
        measured[f"unevaluated:{kind}"] = published[kind] - evaluated[kind]
    return measured


def _text(document: str) -> str:
    return (ROOT / document).read_text(encoding="utf-8")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


@pytest.mark.parametrize("document", LIVE_DOCUMENTS)
def test_every_stated_count_is_the_measured_one(document: str) -> None:
    """Each claim in the prose equals what the vendored files produce."""
    measured = _measured()
    text = _text(document)

    for pattern, quantities in CLAIMS:
        for match in re.finditer(pattern, text):
            for group, quantity in enumerate(quantities, start=1):
                stated = int(match.group(group))
                assert stated == measured[quantity], (
                    f"{document}:{_line_of(text, match.start(group))} states {quantity} "
                    f"as {stated}; the vendored files give {measured[quantity]}"
                )

    for match in PER_KIND.finditer(text):
        kind = match.group(2)
        stated = int(match.group(1))
        assert stated == measured[f"published:{kind}"], (
            f"{document}:{_line_of(text, match.start(1))} states {stated} `{kind}` "
            f"constraints; the vendored files declare {measured[f'published:{kind}']}"
        )


def test_the_claims_are_actually_found_rather_than_matching_nothing() -> None:
    """A pattern set that matches nothing would pass every assertion above.

    Each shape is required to appear at least once somewhere in the live
    documents, so deleting or rewording the sentence it guards fails here
    rather than turning this file into a check that cannot fail.
    """
    corpus = "\n".join(_text(document) for document in LIVE_DOCUMENTS)
    for pattern, _ in CLAIMS:
        assert re.search(pattern, corpus), f"no live document states: {pattern}"
    assert {match.group(2) for match in PER_KIND.finditer(corpus)} == set(KINDS)


@pytest.mark.parametrize("document", LIVE_DOCUMENTS)
def test_no_coverage_number_escapes_a_check(document: str) -> None:
    """A reworded claim fails rather than slipping past the shapes above.

    The shapes are literal sentences, so a rewrite could state a coverage
    number in a form none of them recognise and go unchecked forever. Every
    occurrence of one of the three headline counts therefore has to sit inside
    something this file matched. Rewording is fine; rewording without adding
    the new shape here is not.
    """
    measured = _measured()
    text = _text(document)

    covered: list[tuple[int, int]] = []
    for pattern, _ in CLAIMS:
        covered.extend(match.span() for match in re.finditer(pattern, text))
    covered.extend(match.span() for match in PER_KIND.finditer(text))

    headline = {measured["total"], measured["evaluated"], measured["unevaluated"]}
    for number in sorted(headline):
        for match in re.finditer(rf"(?<!\d){number}(?!\d)", text):
            start, end = match.span()
            assert any(lo <= start and end <= hi for lo, hi in covered), (
                f"{document}:{_line_of(text, start)} states {number} outside any checked "
                "sentence shape; add the shape to CLAIMS in this file"
            )
