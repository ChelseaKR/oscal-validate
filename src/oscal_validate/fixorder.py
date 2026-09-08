"""The order to fix findings in, and why each tier comes where it does.

The ordering is structural, not a ranking. An import that was not supplied has
to come before the references it leaves unsettled; a subtree the validator
could not read before anything under it; identifiers before the references that
name them. Nothing here is a judgment about severity, and nothing here is a
model's opinion.

This lived in ``ai/walkthrough.py``, which is where it was first needed. It is
here now because two surfaces use it -- the model-backed walkthrough and
``--format html``, which groups a reviewer's page the same way -- and a fix
order that two documents state separately is a fix order that will eventually
disagree with itself. ``ai/walkthrough.py`` imports this and adds the labelling
and prompt formatting that are only about a prompt.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .findings import Finding

#: Fix order. Each tier names the codes in it and why it comes where it does.
TIERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "Supply what the document imports",
        "an import that was not supplied, or matched more than one file, leaves every "
        "reference into it unsettled; nothing below can be decided until this is",
        ("IMPORT_NOT_SUPPLIED", "IMPORT_AMBIGUOUS"),
    ),
    (
        "Shape the validator could not read",
        "a subtree the schema walk could not resolve, an object no alternative accepts, or "
        "a value of the wrong JSON type hides everything beneath it from every later check",
        ("SUBTREE_NOT_READ", "NO_SCHEMA_ALTERNATIVE", "TYPE_MISMATCH"),
    ),
    (
        "Required structure",
        "properties the schema requires, forbids, or bounds",
        ("REQUIRED_PROPERTY_MISSING", "PROPERTY_UNDECLARED", "ARRAY_TOO_SHORT"),
    ),
    (
        "Values against their datatypes",
        "a malformed UUID or timestamp is also a broken identifier or a broken sort key",
        ("DATATYPE_MISMATCH", "DATATYPE_BELOW_MINIMUM"),
    ),
    (
        "Identifiers",
        "a duplicated id cannot be referenced unambiguously, so these come before references",
        ("UUID_NOT_UNIQUE", "CONSTRAINT_NOT_UNIQUE", "CONSTRAINT_CARDINALITY"),
    ),
    (
        "Values against NIST's constraints",
        "a value NIST's own constraint layer says is not permitted where it is written",
        ("CONSTRAINT_VALUE_MISMATCH",),
    ),
    (
        "References that resolve to nothing",
        "the effective data model is complete and the target does not exist",
        ("REFERENCE_UNRESOLVED",),
    ),
    (
        "Declared version",
        "the document was judged against OSCAL 1.2.3 whatever it declares (issue #8)",
        ("OSCAL_VERSION_DIFFERS",),
    ),
    (
        "Not settled: UNVERIFIABLE",
        "neither a pass nor a fail; the validator did not decide these either way",
        ("REFERENCE_UNVERIFIABLE", "CONSTRAINT_NOT_EVALUATED", "PATTERN_NOT_CHECKED"),
    ),
    (
        "For the record",
        "imports that were matched, listed so the effective data model is visible",
        ("IMPORT_RESOLVED",),
    ),
)

#: What a code no tier names is placed under. It is placed, not dropped: a
#: grouping that silently omitted a code would hide findings from every surface
#: built on it.
UNKNOWN_TIER = ("Other", "a code this grouping does not know; fix order unstated")

#: The tier whose codes are the ones a run did not settle. Named here so a
#: surface can point a reader at it without matching on the heading text.
UNSETTLED_TIER = "Not settled: UNVERIFIABLE"


@dataclass(frozen=True)
class CodeGroup:
    """Every finding carrying one code, with the tier that places it.

    The field is ``finding_code`` rather than ``code`` because the AST census
    in ``tests/test_finding_code_census.py`` enumerates every ``code=`` keyword
    argument anywhere in the package -- deliberately, so that a finding built
    through a helper cannot escape it. A keyword of that name on a call that
    builds no finding would enter the census as an expression it cannot read,
    and narrowing the census to calls literally spelled ``Finding(...)`` would
    be a real hole in it.
    """

    tier: str
    why: str
    finding_code: str
    severity: str
    findings: tuple[Finding, ...]


def severity_rank(value: str) -> int:
    return {"ERROR": 3, "WARNING": 2, "INFO": 1, "UNVERIFIABLE": 0}.get(value, -1)


def group_by_code(findings: Sequence[Finding]) -> list[CodeGroup]:
    """Every finding into exactly one group, in fix order.

    Groups are ordered by their tier and then by code, so the result depends
    only on which codes are present -- never on the order the findings arrived
    in, which is what makes a rendering built on this byte-stable.
    """
    known = {code: (tier, why) for tier, why, codes in TIERS for code in codes}
    order = {code: index for index, (_, _, codes) in enumerate(TIERS) for code in codes}
    buckets: dict[str, list[Finding]] = {}
    for finding in findings:
        buckets.setdefault(finding.code, []).append(finding)
    groups: list[CodeGroup] = []
    for code in sorted(buckets, key=lambda c: (order.get(c, len(TIERS)), c)):
        tier, why = known.get(code, UNKNOWN_TIER)
        in_group = buckets[code]
        severity = max((f.severity.value for f in in_group), key=severity_rank)
        groups.append(
            CodeGroup(
                tier=tier,
                why=why,
                finding_code=code,
                severity=severity,
                findings=tuple(in_group),
            )
        )
    return groups
