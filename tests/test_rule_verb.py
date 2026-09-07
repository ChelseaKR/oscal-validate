"""``oscal-validate rule``: the citation trail, and the gates that keep it true.

The verb prints provenance, so the failure mode that matters is not a crash --
it is a confident answer that names the wrong source. Three gates stand against
that, and none of them is a string comparison against a sentence written twice.

1. The code map's key set must equal the roster the AST census in
   ``tests/test_finding_code_census.py`` takes from the package, so a new
   finding code cannot arrive without an entry here.
2. A second AST walk pairs each ``code=`` with the ``rule=`` beside it in the
   same ``Finding(...)`` call and compares the pairs to the map, so an entry
   naming a rule the check does not cite fails. Where both are written as
   conditional expressions, the walk pairs them branch by branch -- and refuses
   to do so unless the two conditions are the same expression, because
   otherwise the branches do not correspond.
3. The reasons the verb prints for unevaluated constraint kinds are compared
   against the reasons a real ``CONSTRAINT_NOT_EVALUATED`` finding carries.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from oscal_validate import rules, validate_file
from oscal_validate.cli import main
from oscal_validate.metaschema import load_metaschema
from oscal_validate.rule import (
    CODES,
    CONSTANT,
    CONSTRAINT_LAYER,
    COVERAGE_DOC,
    TEMPLATE,
    TEMPLATE_RETRIEVED,
    TEMPLATE_URL,
    Quotation,
    _render_quotation,
    code_answer,
    constraint_answer,
    skipped_kinds,
)
from oscal_validate.sources import SPECIFICATION, section_at, specification_path

from .conftest import fixture_path
from .test_finding_code_census import ROSTER

ROOT = Path(__file__).resolve().parent.parent
CHECKS = ROOT / "src" / "oscal_validate" / "checks"

#: A ``rule=`` argument that is a call to a local helper, and the rules that
#: helper can return. Named rather than inferred, because the walk cannot
#: follow a function call -- and unnamed indirection is refused below, so a new
#: helper fails this file instead of quietly widening the hole.
INDIRECTION: dict[str, tuple[str, ...]] = {
    "constraint_rule": ("checks.constraints.constraint_rule",),
    "_unsettled_rule": ("rules.CROSS_INSTANCE_SCOPE", "rules.INDEX_NEVER_BUILT"),
}


# -- the map is the source's own ---------------------------------------------


def test_the_map_names_exactly_the_codes_the_package_can_emit() -> None:
    assert set(CODES) == set(ROSTER)


def test_every_named_constant_is_a_real_rule_and_is_quoted_verbatim() -> None:
    for code, entry in CODES.items():
        for reference in entry.produced_by:
            if reference.kind != CONSTANT:
                continue
            rule = getattr(rules, reference.name, None)
            assert rule is not None, f"{code} names rules.{reference.name}, which does not exist"
            answer = code_answer(code)
            assert answer is not None
            quoted = [c.citation for c in answer.citations if c.name.endswith(reference.name)]
            assert rule.citation in quoted, code


def test_every_named_template_is_a_factory_citing_the_vendored_schema() -> None:
    """The template entries print one URL and one date for all of them.

    That is only safe while every factory really does cite the schema, so each
    one is called with sample arguments and its own Rule is read. The
    arguments are throwaway; the URL and the date are the assertion.
    """
    samples: dict[str, tuple[object, ...]] = {
        "required_property_rule": ("catalog", "uuid"),
        "undeclared_property_rule": ("catalog", "extra"),
        "no_alternative_rule": ("part",),
        "type_rule": ("catalog", "object"),
        "datatype_rule": ("TokenDatatype", "a token", "^[a-z]+$"),
        "minimum_rule": ("PositiveIntegerDatatype", "a positive integer", "1"),
        "min_items_rule": ("controls", 1),
    }
    named = {r.name for entry in CODES.values() for r in entry.produced_by if r.kind == TEMPLATE}
    assert named == set(samples), "a template entry with no sample, or the reverse"
    for name, arguments in samples.items():
        factory = getattr(rules, name)
        rule = factory(*arguments)
        assert rule.url == TEMPLATE_URL, name
        assert rule.retrieved == TEMPLATE_RETRIEVED, name


# -- the AST walk: what each check actually cites -----------------------------


class _Pairs(ast.NodeVisitor):
    """Collect ``(code, rule)`` pairs from every ``Finding(...)`` in a module."""

    def __init__(self) -> None:
        self.pairs: set[tuple[str, str]] = set()
        self.literals: dict[str, set[str]] = {}
        self.unresolved: list[str] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.literals.setdefault(target.id, set()).add(node.value.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        keywords = {k.arg: k.value for k in node.keywords if k.arg}
        code = keywords.get("code")
        rule = keywords.get("rule")
        if code is not None and rule is not None:
            self._pair(code, rule)
        self.generic_visit(node)

    def _pair(self, code: ast.expr, rule: ast.expr) -> None:
        if isinstance(code, ast.IfExp) and isinstance(rule, ast.IfExp):
            if ast.unparse(code.test) != ast.unparse(rule.test):
                self.unresolved.append(
                    f"conditional code and rule guarded by different tests: "
                    f"{ast.unparse(code.test)} vs {ast.unparse(rule.test)}"
                )
                return
            self._pair(code.body, rule.body)
            self._pair(code.orelse, rule.orelse)
            return
        for name in self._codes(code):
            for cited in self._rules(rule):
                self.pairs.add((name, cited))

    def _codes(self, node: ast.expr) -> set[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value}
        if isinstance(node, ast.Name) and node.id in self.literals:
            return self.literals[node.id]
        if isinstance(node, ast.IfExp):
            return self._codes(node.body) | self._codes(node.orelse)
        self.unresolved.append(f"code= {ast.unparse(node)}")
        return set()

    def _rules(self, node: ast.expr) -> set[str]:
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            return {f"{node.value.id}.{node.attr}"}
        if isinstance(node, ast.IfExp):
            return self._rules(node.body) | self._rules(node.orelse)
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
                return {f"{function.value.id}.{function.attr}"}
            if isinstance(function, ast.Name) and function.id in INDIRECTION:
                return set(INDIRECTION[function.id])
        self.unresolved.append(f"rule= {ast.unparse(node)}")
        return set()


def _walk_the_checks() -> dict[str, set[str]]:
    cited: dict[str, set[str]] = {}
    sources = sorted(CHECKS.glob("*.py"))
    assert sources, "no check modules found; this walk would pass on nothing"
    for path in sources:
        visitor = _Pairs()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        assert not visitor.unresolved, f"{path.name}: {visitor.unresolved}"
        for code, rule in visitor.pairs:
            cited.setdefault(code, set()).add(rule)
    return cited


def test_the_walk_finds_every_code_the_roster_holds() -> None:
    """A walk that stopped matching would otherwise pass on an empty result."""
    assert set(_walk_the_checks()) == set(ROSTER)


def test_the_map_names_the_rules_the_checks_actually_cite() -> None:
    cited = _walk_the_checks()
    for code, entry in CODES.items():
        declared = {_qualified(reference.kind, reference.name) for reference in entry.produced_by}
        assert declared == cited[code], code


def _qualified(kind: str, name: str) -> str:
    """The name as the source spells it: ``rules.X`` for a name in that module."""
    return name if kind == CONSTRAINT_LAYER else f"rules.{name}"


def test_the_indirection_table_names_no_helper_the_checks_do_not_call() -> None:
    """An entry left behind after its helper is deleted would widen the walk."""
    called: set[str] = set()
    for path in sorted(CHECKS.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called.add(node.func.id)
    assert set(INDIRECTION) <= called, set(INDIRECTION) - called


# -- constraint identifiers ---------------------------------------------------


def test_a_constraint_prints_its_declaration_level_target_and_specification() -> None:
    answer = constraint_answer("oscal-catalog-controls")
    assert answer is not None
    declaration = answer.declarations[0]
    assert declaration.kind == "index"
    assert declaration.level == "ERROR"
    assert declaration.target == "//control"
    assert declaration.declaration.text is not None
    assert 'id="oscal-catalog-controls"' in declaration.declaration.text
    assert declaration.declaration.text.startswith("<index")
    assert declaration.specification is not None
    assert declaration.specification.section.endswith("index Constraints")
    for quotation in (declaration.declaration, declaration.specification):
        assert len(quotation.sha256) == 64
        assert quotation.retrieved


def test_the_quoted_specification_is_verbatim_from_the_pinned_corpus() -> None:
    answer = constraint_answer("oscal-catalog-controls")
    assert answer is not None
    quotation = answer.declarations[0].specification
    assert quotation is not None
    section = section_at(SPECIFICATION, specification_path("index"))
    assert section is not None
    assert quotation.text == section.text


def test_every_published_constraint_kind_resolves_to_a_specification_section() -> None:
    kinds = {constraint.kind for constraint in load_metaschema().constraints}
    assert len(kinds) >= 7
    for kind in sorted(kinds):
        assert section_at(SPECIFICATION, specification_path(kind)) is not None, kind


def test_every_named_constraint_the_metaschema_publishes_can_be_looked_up() -> None:
    named = {c.identifier for c in load_metaschema().constraints if c.identifier}
    assert len(named) > 100
    for identifier in sorted(named):
        assert constraint_answer(identifier) is not None, identifier


def test_an_unevaluated_constraint_prints_its_own_reason_not_its_kinds() -> None:
    skipped = [c for c in load_metaschema().skipped() if c.identifier]
    assert skipped, "the metaschema publishes constraints this tool skips"
    constraint = skipped[0]
    answer = constraint_answer(constraint.identifier)
    assert answer is not None
    declaration = answer.declarations[0]
    assert declaration.evaluated is False
    assert declaration.not_evaluated_because == constraint.skipped
    assert declaration.not_evaluated_because


def test_every_named_constraint_has_a_declaration_to_quote() -> None:
    """The one thing this verb must never do is claim a constraint exists and
    then print nothing under it. ``(this file declares no element ...)`` is a
    real branch, kept for a re-vendoring that changes the spelling; it must not
    be reachable from any constraint in the snapshot that ships today."""
    named = sorted({c.identifier for c in load_metaschema().constraints if c.identifier})
    assert len(named) > 100
    for identifier in named:
        answer = constraint_answer(identifier)
        assert answer is not None, identifier
        for declaration in answer.declarations:
            assert declaration.declaration.text is not None, identifier


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("oscal-metadata-location-address-cardinality", ("min occurs",)),
        ("oscal-back-matter-resource-prop-published-datatype", ("datatype",)),
        ("oscal-back-matter-resource-citation-title", ("test",)),
        ("oscal-metadata-revision-link-rel-types", ("allow-other",)),
        ("oscal-index-metadata-roles", ("index",)),
        ("oscal-assessment-objective-cardinality", ("max occurs",)),
        ("oscal-metadata-party-type-values", ("declared on flag",)),
        ("oscal-unique-metadata-doc-id", ("key fields",)),
    ],
)
def test_each_constraint_kind_prints_the_attributes_that_kind_carries(
    identifier: str, expected: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["rule", identifier]) == 0
    out = capsys.readouterr().out
    for label in expected:
        assert f"\n{label}: " in out, f"{identifier} did not print {label}"


def test_a_declaration_that_cannot_be_quoted_says_so_rather_than_printing_nothing() -> None:
    quotation = Quotation(
        source="vendor:example.xml",
        url="https://example.invalid/",
        retrieved="2026-01-01",
        sha256="0" * 64,
        text=None,
    )
    rendered = "\n".join(_render_quotation("declaration", quotation))
    assert "declares no element with that identifier" in rendered
    assert quotation.to_dict()["text"] is None
    assert "section" not in quotation.to_dict()


def test_a_constraint_layer_citation_carries_no_url_of_its_own() -> None:
    answer = code_answer("CONSTRAINT_CARDINALITY")
    assert answer is not None
    payload = answer.to_dict()
    rules_payload = payload["rules"]
    assert isinstance(rules_payload, list)
    assert "url" not in rules_payload[0]
    assert rules_payload[0]["citation"] is None
    assert "not_evaluated" not in payload


def test_a_constraint_declared_in_no_module_is_not_invented() -> None:
    assert constraint_answer("oscal-not-a-constraint") is None
    assert constraint_answer("") is None


# -- finding codes ------------------------------------------------------------


def test_the_unevaluated_kinds_the_verb_prints_are_the_ones_a_report_carries() -> None:
    """The verb and the ``CONSTRAINT_NOT_EVALUATED`` finding read one mapping.

    If they ever came apart, a user asking why a constraint did not fire would
    be told something the report contradicts.
    """
    findings = validate_file(fixture_path("clean_catalog.json"))
    reported = {f.prop: f.message for f in findings if f.code == "CONSTRAINT_NOT_EVALUATED"}
    assert reported, "the fixture must produce coverage findings for this to mean anything"
    printed = {kind.kind: kind for kind in skipped_kinds()}
    assert set(printed) == set(reported)
    for kind, message in reported.items():
        assert printed[kind].because in message, kind
        assert f"{printed[kind].published} {kind} constraint(s)" in message


def test_a_finding_code_names_every_rule_that_can_produce_it() -> None:
    answer = code_answer("REFERENCE_UNVERIFIABLE")
    assert answer is not None
    names = [citation.name for citation in answer.citations]
    assert names == ["rules.CROSS_INSTANCE_SCOPE", "rules.INDEX_NEVER_BUILT"]
    assert all(citation.citation for citation in answer.citations)


def test_a_constraint_layer_code_points_at_the_coverage_table() -> None:
    answer = code_answer("CONSTRAINT_NOT_UNIQUE")
    assert answer is not None
    (citation,) = answer.citations
    assert citation.kind == CONSTRAINT_LAYER
    assert citation.citation is None
    assert COVERAGE_DOC in citation.note


def test_a_prose_rule_names_the_corpus_page_it_was_quoted_from() -> None:
    answer = code_answer("UUID_NOT_UNIQUE")
    assert answer is not None
    (citation,) = answer.citations
    assert citation.quoted_from is not None
    assert citation.quoted_from.source == "identifier-use"
    assert citation.quoted_from.retrieved
    assert len(citation.quoted_from.sha256) == 64


def test_a_template_rule_says_the_citation_is_completed_per_finding() -> None:
    answer = code_answer("REQUIRED_PROPERTY_MISSING")
    assert answer is not None
    (citation,) = answer.citations
    assert citation.kind == TEMPLATE
    assert citation.citation is None
    assert citation.url == TEMPLATE_URL
    assert "composed for each finding" in citation.note


def test_an_unknown_code_is_not_answered() -> None:
    assert code_answer("NOT_A_CODE") is None


# -- the command --------------------------------------------------------------


def test_the_verb_prints_a_constraint_and_exits_clean(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["rule", "oscal-catalog-controls"]) == 0
    out = capsys.readouterr().out
    assert "constraint: oscal-catalog-controls" in out
    assert "level: ERROR" in out
    assert '<index id="oscal-catalog-controls"' in out
    assert "index Constraints" in out
    assert "sha256: " in out


def test_the_verb_prints_a_finding_code_and_exits_clean(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["rule", "CONSTRAINT_NOT_EVALUATED"]) == 0
    out = capsys.readouterr().out
    assert "finding code: CONSTRAINT_NOT_EVALUATED" in out
    assert "allowed-values:" in out
    assert COVERAGE_DOC in out


def test_an_unknown_identifier_is_exit_two_with_no_partial_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["rule", "oscal-nope"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "oscal-nope" in captured.err


def test_json_output_is_valid_and_carries_the_hashes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["rule", "oscal-catalog-controls", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    declaration = payload["declarations"][0]
    assert declaration["kind"] == "index"
    assert declaration["declaration"]["sha256"]
    assert declaration["specification"]["sha256"]
    assert declaration["evaluated"] is True


def test_an_unevaluated_constraint_json_carries_its_reason_and_the_coverage_doc(
    capsys: pytest.CaptureFixture[str],
) -> None:
    constraint = next(c for c in load_metaschema().skipped() if c.identifier)
    assert main(["rule", constraint.identifier, "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    declaration = payload["declarations"][0]
    assert declaration["evaluated"] is False
    assert declaration["not_evaluated_because"] == constraint.skipped
    assert declaration["coverage"] == COVERAGE_DOC


def _run(identifier: str, seed: str) -> bytes:
    environment = dict(os.environ, PYTHONHASHSEED=seed)
    result = subprocess.run(
        [sys.executable, "-m", "oscal_validate", "rule", identifier, "--format", "json"],
        capture_output=True,
        check=True,
        cwd=ROOT,
        env=environment,
    )
    return result.stdout


def test_the_output_is_byte_identical_across_processes_and_hash_seeds() -> None:
    """Two runs in one interpreter prove nothing about ordering, so this runs
    three separate processes under three different hash seeds."""
    outputs = {_run("CONSTRAINT_NOT_EVALUATED", seed) for seed in ("0", "1", "12345")}
    assert len(outputs) == 1


def test_the_verb_needs_no_document_and_no_optional_dependency() -> None:
    """It is the answer with no model in it: a fresh process runs the verb and
    reports every loaded module from the AI layer or an SDK. There must be
    none, which is what makes this usable from the Action."""
    script = (
        "import sys\n"
        "from oscal_validate.cli import main\n"
        "assert main(['rule', 'oscal-catalog-controls']) == 0\n"
        "loaded = sorted(m for m in sys.modules if m.startswith(('oscal_validate.ai', "
        "'anthropic', 'httpx', 'boto')))\n"
        "print(loaded)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False, cwd=ROOT
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "[]"
