"""``oscal-validate rule`` -- the citation trail, offline and with no model.

``explain`` spends most of its value before it calls a model: it gathers the
constraint NIST declared, the level NIST published, the target expression, the
Metaschema specification's section for that kind, and the hashes of the bytes
all of it was read from. That gathering is deterministic. This verb is it,
made a first-class command, so the citation trail is available to a user who
will not send a document to a model, to the GitHub Action, which never runs a
model-backed command, and to anyone with no optional dependency installed.

Two identifiers are accepted and they cannot be confused: a finding code, which
this tool spells in upper case with underscores, and a constraint identifier,
which NIST spells in lower case with hyphens. An identifier that is neither is
exit 2 with nothing printed, because a partial answer about provenance is worse
than no answer.

Nothing here paraphrases. Every quoted passage is verbatim from a hash-pinned
file, and every quotation is printed beside the SHA-256 of the bytes it came
from and the date those bytes were retrieved.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from . import rules
from .metaschema import UNEVALUATED_KINDS, Constraint, load_metaschema
from .sources import (
    SOURCE_FOR_URL,
    SPECIFICATION,
    constraint_snippet,
    load,
    section_at,
    specification_path,
)

#: Where the per-constraint reasons and the full published list are.
COVERAGE_DOC = "docs/CONSTRAINT-COVERAGE.md"

#: The reason printed for a skipped constraint whose kind has no entry in
#: ``UNEVALUATED_KINDS``. It is the same sentence ``checks/constraints.py``
#: prints, and ``tests/test_rule_verb.py`` holds the two together.
GENERIC_SKIP_REASON = "their target expressions are outside the Metapath subset this tool parses"

CONSTANT = "constant"
TEMPLATE = "template"
CONSTRAINT_LAYER = "constraint"

#: Every rule template in :mod:`oscal_validate.rules` cites the vendored JSON
#: Schema. Written once rather than once per entry, and
#: ``tests/test_rule_verb.py`` calls each factory and checks that it holds.
TEMPLATE_URL = rules.SCHEMA_URL
TEMPLATE_RETRIEVED = rules.RETRIEVED

TEMPLATE_NOTE = (
    "the citation is composed for each finding from the assembly and property names the "
    "schema declares, so it exists only beside a finding"
)
LAYER_NOTE = (
    "the citation names the constraint NIST declared, its kind, level, module, target and "
    "key. Run `oscal-validate rule <constraint-id>` for one of them; "
    f"{COVERAGE_DOC} lists every constraint NIST publishes and whether it is evaluated here"
)


# -- the answer shapes -------------------------------------------------------


@dataclass(frozen=True)
class Quotation:
    """Verbatim text from one hash-pinned file, with the bytes it came from.

    ``text`` is None where the named file declares no element with that
    identifier. That is reported rather than rendered as an empty quotation:
    an absent declaration and an empty one are different facts.
    """

    source: str
    url: str
    retrieved: str
    sha256: str
    text: str | None
    section: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "source": self.source,
            "url": self.url,
            "retrieved": self.retrieved,
            "sha256": self.sha256,
            "text": self.text,
        }
        if self.section:
            payload["section"] = self.section
        return payload


@dataclass(frozen=True)
class Declaration:
    """One constraint as NIST declared it, in one module."""

    kind: str
    level: str
    module: str
    declared_on: str
    target: str
    models: tuple[str, ...] | None
    evaluated: bool
    not_evaluated_because: str
    key_fields: tuple[str, ...]
    index_name: str
    regex: str
    datatype: str
    test: str
    allow_other: str
    declared_on_flag: str
    min_occurs: int | None
    max_occurs: int | None
    declaration: Quotation
    specification: Quotation | None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": self.kind,
            "level": self.level,
            "module": self.module,
            "declared_on": self.declared_on,
            "target": self.target,
            "models": list(self.models) if self.models is not None else None,
            "evaluated": self.evaluated,
            "declaration": self.declaration.to_dict(),
        }
        if not self.evaluated:
            payload["not_evaluated_because"] = self.not_evaluated_because
            payload["coverage"] = COVERAGE_DOC
        for name, value in self._optional_strings():
            if value:
                payload[name] = value
        if self.key_fields:
            payload["key_fields"] = list(self.key_fields)
        if self.min_occurs is not None:
            payload["min_occurs"] = self.min_occurs
        if self.max_occurs is not None:
            payload["max_occurs"] = self.max_occurs
        if self.specification is not None:
            payload["specification"] = self.specification.to_dict()
        return payload

    def _optional_strings(self) -> tuple[tuple[str, str], ...]:
        return (
            ("index_name", self.index_name),
            ("regex", self.regex),
            ("datatype", self.datatype),
            ("test", self.test),
            ("allow_other", self.allow_other),
            ("declared_on_flag", self.declared_on_flag),
        )


@dataclass(frozen=True)
class ConstraintAnswer:
    identifier: str
    declarations: tuple[Declaration, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "identifier": self.identifier,
            "declarations": [d.to_dict() for d in self.declarations],
        }


@dataclass(frozen=True)
class RuleCitation:
    """One rule that can produce a finding code."""

    name: str
    kind: str
    citation: str | None
    url: str
    retrieved: str
    note: str
    quoted_from: Quotation | None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "kind": self.kind,
            "citation": self.citation,
        }
        if self.url:
            payload["url"] = self.url
            payload["retrieved"] = self.retrieved
        if self.note:
            payload["note"] = self.note
        if self.quoted_from is not None:
            payload["quoted_from"] = self.quoted_from.to_dict()
        return payload


@dataclass(frozen=True)
class SkippedKind:
    kind: str
    published: int
    because: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "published": self.published,
            "because": self.because,
            "coverage": COVERAGE_DOC,
        }


@dataclass(frozen=True)
class CodeAnswer:
    """One finding code and every rule that can produce it.

    The field is ``finding_code`` rather than ``code`` because the AST census
    in ``tests/test_finding_code_census.py`` enumerates every ``code=``
    keyword argument anywhere in the package -- deliberately, so that a
    finding built through a helper cannot escape it. A keyword of that name on
    a call that builds no finding would enter the census as an expression it
    cannot read. Renaming the field here is the cheaper half of that trade:
    narrowing the census to calls literally spelled ``Finding(...)`` would be
    a real hole in it.
    """

    finding_code: str
    reports: str
    emitted_by: tuple[str, ...]
    citations: tuple[RuleCitation, ...]
    not_evaluated: tuple[SkippedKind, ...]

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.finding_code,
            "reports": self.reports,
            "emitted_by": list(self.emitted_by),
            "rules": [c.to_dict() for c in self.citations],
        }
        if self.not_evaluated:
            payload["not_evaluated"] = [k.to_dict() for k in self.not_evaluated]
        return payload


# -- what each finding code is made under ------------------------------------


@dataclass(frozen=True)
class CodeRule:
    """One way a finding code gets its citation.

    ``kind`` is ``constant`` for a fixed :class:`~oscal_validate.findings.Rule`
    in :mod:`oscal_validate.rules`, which is quoted verbatim; ``template`` for
    a factory there whose citation is completed from the document being
    validated, so only its source can be shown; and ``constraint`` for the
    constraint layer, where the citation names the constraint NIST declared
    and ``rule <constraint-id>`` prints it.
    """

    name: str
    kind: str


@dataclass(frozen=True)
class CodeEntry:
    what: str
    emitted_by: tuple[str, ...]
    produced_by: tuple[CodeRule, ...]


def _constant(name: str) -> CodeRule:
    return CodeRule(name=name, kind=CONSTANT)


def _template(name: str) -> CodeRule:
    return CodeRule(name=name, kind=TEMPLATE)


_LAYER = CodeRule(name="checks.constraints.constraint_rule", kind=CONSTRAINT_LAYER)

#: What every finding code reports, and which rules can produce it.
#:
#: Hand-written, and held to the source two ways by
#: ``tests/test_rule_verb.py``: the key set must equal the roster the AST
#: census in ``tests/test_finding_code_census.py`` takes from the package, so a
#: new code cannot arrive without an entry here; and a second AST walk pairs
#: each ``code=`` with the ``rule=`` beside it in the same ``Finding(...)``
#: call, so an entry naming the wrong rule fails rather than misinforming a
#: reader.
CODES: dict[str, CodeEntry] = {
    "ARRAY_TOO_SHORT": CodeEntry(
        what="an array is present with fewer items than the schema's minItems allows",
        emitted_by=("checks/structure.py",),
        produced_by=(_template("min_items_rule"),),
    ),
    "CONSTRAINT_CARDINALITY": CodeEntry(
        what="a has-cardinality constraint's target selected too few or too many nodes",
        emitted_by=("checks/constraints.py",),
        produced_by=(_LAYER,),
    ),
    "CONSTRAINT_NOT_EVALUATED": CodeEntry(
        what=(
            "one report per constraint kind this tool did not evaluate, so that "
            "'no findings' can never be read as 'every published constraint passed'"
        ),
        emitted_by=("checks/constraints.py",),
        produced_by=(_constant("NOT_WALKED_POLICY"),),
    ),
    "CONSTRAINT_NOT_UNIQUE": CodeEntry(
        what="two nodes share a key an is-unique or index constraint requires to be unique",
        emitted_by=("checks/constraints.py",),
        produced_by=(_LAYER,),
    ),
    "CONSTRAINT_VALUE_MISMATCH": CodeEntry(
        what="a value does not match the regular expression a matches constraint declares",
        emitted_by=("checks/constraints.py",),
        produced_by=(_LAYER,),
    ),
    "DATATYPE_BELOW_MINIMUM": CodeEntry(
        what="a value is below the minimum the schema declares for its datatype",
        emitted_by=("checks/datatypes.py",),
        produced_by=(_template("minimum_rule"),),
    ),
    "DATATYPE_MISMATCH": CodeEntry(
        what="a value does not match the pattern the schema declares for its datatype",
        emitted_by=("checks/datatypes.py",),
        produced_by=(_template("datatype_rule"),),
    ),
    "IMPORT_AMBIGUOUS": CodeEntry(
        what="more than one supplied document answers to the file name an import names",
        emitted_by=("checks/imports.py",),
        produced_by=(_constant("EFFECTIVE_DATA_MODEL"),),
    ),
    "IMPORT_NOT_SUPPLIED": CodeEntry(
        what="a document this one imports was not supplied, so the data model is incomplete",
        emitted_by=("checks/imports.py",),
        produced_by=(_constant("EFFECTIVE_DATA_MODEL"),),
    ),
    "IMPORT_RESOLVED": CodeEntry(
        what="an import was matched to a supplied document and its identifiers admitted",
        emitted_by=("checks/imports.py",),
        produced_by=(_constant("EFFECTIVE_DATA_MODEL"),),
    ),
    "NO_SCHEMA_ALTERNATIVE": CodeEntry(
        what="an object satisfies none of the alternatives the schema declares for it",
        emitted_by=("checks/structure.py",),
        produced_by=(_template("no_alternative_rule"),),
    ),
    "OSCAL_VERSION_DIFFERS": CodeEntry(
        what="the document names an OSCAL release other than the vendored snapshot's",
        emitted_by=("checks/versions.py",),
        produced_by=(_constant("OSCAL_VERSION_FIELD"),),
    ),
    "PATTERN_NOT_CHECKED": CodeEntry(
        what=(
            "the schema declares a regular expression this tool cannot compile, so the "
            "value was reported as unchecked rather than approximated"
        ),
        emitted_by=("checks/datatypes.py",),
        produced_by=(_constant("UNCOMPILABLE_PATTERN"),),
    ),
    "PROPERTY_UNDECLARED": CodeEntry(
        what="a property appears where the schema declares additionalProperties false",
        emitted_by=("checks/structure.py",),
        produced_by=(_template("undeclared_property_rule"),),
    ),
    "REFERENCE_UNRESOLVED": CodeEntry(
        what=(
            "a reference names an identifier declared nowhere in the effective data "
            "model, and the data model was complete enough to settle that"
        ),
        emitted_by=("checks/constraints.py", "checks/references.py"),
        produced_by=(_LAYER, _constant("EFFECTIVE_DATA_MODEL")),
    ),
    "REFERENCE_UNVERIFIABLE": CodeEntry(
        what=(
            "a reference could not be settled from the documents supplied; never a pass "
            "and never a failure of the document"
        ),
        emitted_by=("checks/constraints.py", "checks/references.py"),
        produced_by=(_constant("CROSS_INSTANCE_SCOPE"), _constant("INDEX_NEVER_BUILT")),
    ),
    "REQUIRED_PROPERTY_MISSING": CodeEntry(
        what="a property the schema lists as required is absent",
        emitted_by=("checks/structure.py",),
        produced_by=(_template("required_property_rule"),),
    ),
    "SUBTREE_NOT_READ": CodeEntry(
        what=(
            "a subtree was left unread because the schema combines alternatives in a form "
            "this tool does not resolve; an unread subtree is not a clean one"
        ),
        emitted_by=("checks/structure.py",),
        produced_by=(_constant("NOT_WALKED_POLICY"),),
    ),
    "TYPE_MISMATCH": CodeEntry(
        what="a value is of a different JSON type from the one the schema declares",
        emitted_by=("checks/structure.py",),
        produced_by=(_template("type_rule"),),
    ),
    "UUID_NOT_UNIQUE": CodeEntry(
        what="two objects in one document carry the same globally-unique UUID",
        emitted_by=("checks/identifiers.py",),
        produced_by=(_constant("UUID_GLOBALLY_UNIQUE"),),
    ),
}


# -- gathering ---------------------------------------------------------------


def constraints_named(identifier: str) -> list[Constraint]:
    """Every published constraint carrying this identifier, in module order."""
    if not identifier:
        return []
    return [c for c in load_metaschema().constraints if c.identifier == identifier]


def skipped_kinds() -> tuple[SkippedKind, ...]:
    """Per kind: how many constraints NIST publishes that this tool skips, and why.

    The reason is read from the same mapping ``checks/constraints.py`` reads,
    so the verb and the ``CONSTRAINT_NOT_EVALUATED`` finding cannot say
    different things about one kind.
    """
    counted: defaultdict[str, int] = defaultdict(int)
    for constraint in load_metaschema().skipped():
        counted[constraint.kind] += 1
    return tuple(
        SkippedKind(
            kind=kind,
            published=count,
            because=UNEVALUATED_KINDS.get(kind, GENERIC_SKIP_REASON),
        )
        for kind, count in sorted(counted.items())
    )


def _quotation(identifier: str, text: str | None, section: str = "") -> Quotation:
    source = load(identifier)
    if source is None:  # pragma: no cover - every id reaching here is a real source
        raise KeyError(identifier)
    return Quotation(
        source=identifier,
        url=source.url,
        retrieved=source.retrieved,
        sha256=source.digest,
        text=text,
        section=section,
    )


def _specification(kind: str) -> Quotation | None:
    section = section_at(SPECIFICATION, specification_path(kind))
    if section is None:
        return None
    return _quotation(SPECIFICATION, section.text, section.label)


def constraint_answer(identifier: str) -> ConstraintAnswer | None:
    """Everything published about one constraint identifier, or None if unknown."""
    found = constraints_named(identifier)
    if not found:
        return None
    return ConstraintAnswer(
        identifier=identifier,
        declarations=tuple(_declaration(constraint) for constraint in found),
    )


def _declaration(constraint: Constraint) -> Declaration:
    return Declaration(
        kind=constraint.kind,
        level=constraint.level,
        module=constraint.module,
        declared_on=constraint.context,
        target=constraint.target,
        models=constraint.models,
        evaluated=constraint.evaluated,
        not_evaluated_because=constraint.skipped,
        key_fields=tuple(field.source for field in constraint.key_fields),
        index_name=constraint.index_name,
        regex=constraint.regex,
        datatype=constraint.datatype,
        test=constraint.test,
        allow_other=constraint.allow_other,
        declared_on_flag=constraint.declared_on_flag,
        min_occurs=constraint.min_occurs,
        max_occurs=constraint.max_occurs,
        declaration=_quotation(
            f"vendor:{constraint.module}",
            constraint_snippet(constraint.identifier, constraint.module),
        ),
        specification=_specification(constraint.kind),
    )


def code_answer(code: str) -> CodeAnswer | None:
    """Every rule that can produce one finding code, or None if unknown."""
    entry = CODES.get(code)
    if entry is None:
        return None
    return CodeAnswer(
        finding_code=code,
        reports=entry.what,
        emitted_by=entry.emitted_by,
        citations=tuple(_citation(reference) for reference in entry.produced_by),
        not_evaluated=skipped_kinds() if code == "CONSTRAINT_NOT_EVALUATED" else (),
    )


def _citation(reference: CodeRule) -> RuleCitation:
    if reference.kind == CONSTANT:
        rule = getattr(rules, reference.name)
        page = SOURCE_FOR_URL.get(rule.url)
        return RuleCitation(
            name=f"rules.{reference.name}",
            kind=CONSTANT,
            citation=rule.citation,
            url=rule.url,
            retrieved=rule.retrieved,
            note="",
            quoted_from=_quotation(page, None) if page is not None else None,
        )
    if reference.kind == TEMPLATE:
        return RuleCitation(
            name=f"rules.{reference.name}",
            kind=TEMPLATE,
            citation=None,
            url=TEMPLATE_URL,
            retrieved=TEMPLATE_RETRIEVED,
            note=TEMPLATE_NOTE,
            quoted_from=None,
        )
    return RuleCitation(
        name=reference.name,
        kind=CONSTRAINT_LAYER,
        citation=None,
        url="",
        retrieved="",
        note=LAYER_NOTE,
        quoted_from=None,
    )


# -- rendering ---------------------------------------------------------------


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line if line else line for line in text.split("\n"))


def render_constraint(answer: ConstraintAnswer) -> str:
    lines = [f"constraint: {answer.identifier}"]
    for declaration in answer.declarations:
        lines.append("")
        lines.extend(_render_declaration(declaration))
    return "\n".join(lines)


def _render_declaration(declaration: Declaration) -> list[str]:
    models = declaration.models
    lines = [
        f"kind: {declaration.kind}",
        f"level: {declaration.level}",
        f"declared on: {declaration.declared_on}",
        f"target: {declaration.target}",
        "applies to: " + (", ".join(models) if models is not None else "every model"),
    ]
    if declaration.key_fields:
        lines.append(f"key fields: {', '.join(declaration.key_fields)}")
    for label, value in (
        ("index", declaration.index_name),
        ("regex", declaration.regex),
        ("datatype", declaration.datatype),
        ("test", declaration.test),
        ("allow-other", declaration.allow_other),
        ("declared on flag", declaration.declared_on_flag),
    ):
        if value:
            lines.append(f"{label}: {value}")
    for label, number in (
        ("min occurs", declaration.min_occurs),
        ("max occurs", declaration.max_occurs),
    ):
        if number is not None:
            lines.append(f"{label}: {number}")
    if declaration.evaluated:
        lines.append("evaluated: yes")
    else:
        lines.append("evaluated: no")
        lines.append(f"    why not: {declaration.not_evaluated_because}")
        lines.append(f"    every constraint and its reason: {COVERAGE_DOC}")
    lines.append("")
    lines.extend(_render_quotation("declaration", declaration.declaration))
    if declaration.specification is not None:
        lines.append("")
        lines.extend(_render_quotation("specification", declaration.specification))
    return lines


def _render_quotation(label: str, quotation: Quotation) -> list[str]:
    heading = f"{label}: {quotation.source}"
    if quotation.section:
        heading += f", section {quotation.section}"
    lines = [
        heading,
        f"    source: {quotation.url} (retrieved {quotation.retrieved})",
        f"    sha256: {quotation.sha256}",
    ]
    if quotation.text is None:
        lines.append("    (this file declares no element with that identifier)")
        return lines
    lines.append("")
    lines.append(_indent(quotation.text))
    return lines


def render_code(answer: CodeAnswer) -> str:
    lines = [
        f"finding code: {answer.finding_code}",
        f"reports: {answer.reports}",
        f"emitted by: {', '.join(answer.emitted_by)}",
        "",
        "rules that can produce it:",
    ]
    for index, citation in enumerate(answer.citations, start=1):
        lines.append("")
        lines.append(f"  {index}. {citation.name} ({citation.kind})")
        if citation.url:
            lines.append(f"     source: {citation.url} (retrieved {citation.retrieved})")
        if citation.quoted_from is not None:
            lines.append(
                f"     quoted text in the corpus: {citation.quoted_from.source} "
                f"(retrieved {citation.quoted_from.retrieved}), "
                f"sha256 {citation.quoted_from.sha256}"
            )
        if citation.citation is not None:
            lines.append("")
            lines.append(_indent(citation.citation, "     "))
        if citation.note:
            lines.append(f"     {citation.note}")
    if answer.not_evaluated:
        lines.append("")
        lines.append("constraint kinds this tool does not evaluate:")
        for kind in answer.not_evaluated:
            lines.append("")
            lines.append(f"  {kind.kind}: {kind.published} published, not evaluated")
            lines.append(f"     because {kind.because}")
        lines.append("")
        lines.append(f"every constraint and its own reason: {COVERAGE_DOC}")
    return "\n".join(lines)


# -- the command -------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oscal-validate rule",
        description=(
            "Print the citation trail for one constraint identifier or one finding "
            "code: the declaring element verbatim from the vendored metaschema module, "
            "NIST's declared level, the target expression and whether this tool "
            "evaluates it, and the Metaschema specification's section for that kind -- "
            "each beside the SHA-256 of the bytes it was read from. Offline, "
            "deterministic, and no model is called."
        ),
    )
    parser.add_argument(
        "identifier",
        help=(
            "a NIST constraint identifier (for example oscal-catalog-controls) or a "
            "finding code this tool emits (for example REFERENCE_UNVERIFIABLE)"
        ),
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    return parser


def main(argv: Sequence[str]) -> int:
    args = build_parser().parse_args(list(argv)[1:])
    identifier = str(args.identifier)
    code = code_answer(identifier)
    constraint = constraint_answer(identifier) if code is None else None
    if code is None and constraint is None:
        print(
            f"oscal-validate: no constraint and no finding code is named {identifier!r}. "
            f"Constraint identifiers are listed in {COVERAGE_DOC}; finding codes are "
            "listed in the README.",
            file=sys.stderr,
        )
        return 2
    answer = code if code is not None else constraint
    if answer is None:  # pragma: no cover - the branch above returned already
        raise AssertionError(identifier)
    if args.format == "json":
        print(json.dumps(answer.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    elif isinstance(answer, CodeAnswer):
        print(render_code(answer))
    else:
        print(render_constraint(answer))
    return 0
