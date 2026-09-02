"""Every finding code this tool can emit must have a witness that emits it.

A rule the source can produce, the README lists, and no test ever trips is a
rule nobody would notice losing. It survives a coverage floor when the module
around it is otherwise well covered, and deleting it turns nothing red. Two of
this tool's nineteen codes were in that position, ``CONSTRAINT_CARDINALITY``
and ``SUBTREE_NOT_READ``, and this file is what stops a third from arriving
unremarked.

The census is taken from the source by AST, not by pattern. A regular
expression over ``[A-Z_]+`` misses a code carrying a digit, and it cannot see
which of the strings it found actually reach the ``code=`` parameter. This walk
visits every call in the package, takes the ``code=`` keyword, and resolves it
through conditional expressions and through local names bound to string
literals in the same function, which is how ``checks/imports.py`` writes its
three.

Two assertions follow from it. The enumerated set must equal ``ROSTER``, so a
new code cannot arrive silently. Every code in ``ROSTER`` must be produced by
one of the witnesses below, run for real against a document, so a code cannot
sit in the source unexercised.
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any

import pytest

from oscal_validate import validate_file

from .conftest import fixture_path, load_fixture, write

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "oscal_validate"

#: Every code the package can emit, as of this commit. Adding a code means
#: adding a witness below; the census test fails until both are done.
ROSTER = frozenset(
    {
        "ARRAY_TOO_SHORT",
        "CONSTRAINT_CARDINALITY",
        "CONSTRAINT_NOT_EVALUATED",
        "CONSTRAINT_NOT_UNIQUE",
        "CONSTRAINT_VALUE_MISMATCH",
        "DATATYPE_BELOW_MINIMUM",
        "DATATYPE_MISMATCH",
        "IMPORT_AMBIGUOUS",
        "IMPORT_NOT_SUPPLIED",
        "IMPORT_RESOLVED",
        "NO_SCHEMA_ALTERNATIVE",
        "OSCAL_VERSION_DIFFERS",
        "PATTERN_NOT_CHECKED",
        "PROPERTY_UNDECLARED",
        "REFERENCE_UNRESOLVED",
        "REFERENCE_UNVERIFIABLE",
        "REQUIRED_PROPERTY_MISSING",
        "SUBTREE_NOT_READ",
        "TYPE_MISMATCH",
        "UUID_NOT_UNIQUE",
    }
)


class _CodeCensus(ast.NodeVisitor):
    """Collect the string values a ``code=`` keyword can take in one module.

    ``literals`` holds every name in the module bound to a string constant,
    which is enough for the one call site that passes a variable. An expression
    this walk cannot reduce to string constants is recorded in ``unresolved``
    rather than dropped, because a census that silently skips what it cannot
    read is the failure this file exists to prevent.
    """

    def __init__(self) -> None:
        self.codes: set[str] = set()
        self.unresolved: list[str] = []
        self.literals: dict[str, set[str]] = {}

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.literals.setdefault(target.id, set()).add(node.value.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for keyword in node.keywords:
            if keyword.arg == "code":
                self._resolve(keyword.value, node.lineno)
        self.generic_visit(node)

    def _resolve(self, node: ast.expr, lineno: int) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            self.codes.add(node.value)
        elif isinstance(node, ast.IfExp):
            self._resolve(node.body, lineno)
            self._resolve(node.orelse, lineno)
        elif isinstance(node, ast.Name) and node.id in self.literals:
            self.codes.update(self.literals[node.id])
        else:
            self.unresolved.append(f"line {lineno}: {ast.dump(node)[:80]}")


def _census() -> tuple[set[str], list[str]]:
    codes: set[str] = set()
    unresolved: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        visitor = _CodeCensus()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        codes |= visitor.codes
        unresolved += [f"{path.relative_to(PACKAGE)} {detail}" for detail in visitor.unresolved]
    return codes, unresolved


def test_the_census_reads_every_source_file() -> None:
    # A census over an empty file list would agree with an empty roster and
    # report success having read nothing.
    modules = sorted(PACKAGE.rglob("*.py"))
    assert len(modules) >= 25, f"only {len(modules)} module(s) found under {PACKAGE}"


def test_every_code_the_source_can_emit_is_on_the_roster() -> None:
    codes, unresolved = _census()
    assert not unresolved, f"code= expressions this census could not read: {unresolved}"
    assert codes == set(ROSTER), {
        "in the source but not on the roster": sorted(codes - set(ROSTER)),
        "on the roster but not in the source": sorted(set(ROSTER) - codes),
    }


# -- the witnesses ------------------------------------------------------------
#
# Each returns a document, and the resolve list to validate it with, chosen so
# that running the real validator over it produces the code it is named for.


def _catalog() -> Any:
    return load_fixture("clean_catalog.json")


def _profile() -> Any:
    return load_fixture("clean_profile.json")


def _party_uuid(catalog: Any) -> str:
    uuid: str = catalog["catalog"]["metadata"]["parties"][0]["uuid"]
    return uuid


def _witness_required_property_missing() -> Any:
    document = _catalog()
    del document["catalog"]["metadata"]["last-modified"]
    return document


def _witness_property_undeclared() -> Any:
    document = _catalog()
    document["catalog"]["metadata"]["invented-property"] = "hello"
    return document


def _witness_type_mismatch() -> Any:
    document = _catalog()
    document["catalog"]["metadata"] = "a string where an assembly belongs"
    return document


def _witness_array_too_short() -> Any:
    document = _catalog()
    document["catalog"]["groups"][0]["controls"] = []
    return document


def _witness_no_schema_alternative() -> Any:
    # A group may hold controls or groups, never both.
    document = _catalog()
    document["catalog"]["groups"][0]["groups"] = [{"id": "sub", "title": "Sub"}]
    return document


def _witness_subtree_not_read() -> Any:
    document = _catalog()
    document["catalog"]["metadata"]["parties"][0] = "not an object"
    return document


def _witness_datatype_mismatch() -> Any:
    document = _catalog()
    document["catalog"]["metadata"]["last-modified"] = "2026-08-14T00:00:00"
    return document


def _witness_datatype_below_minimum() -> Any:
    """``port-range/start`` is one of the two ``NonNegativeIntegerDatatype`` sites."""
    return {
        "component-definition": {
            "uuid": "11111111-2222-4333-8444-555555555551",
            "metadata": {
                "title": "Ports",
                "last-modified": "2026-08-14T00:00:00Z",
                "version": "1",
                "oscal-version": "1.2.3",
            },
            "components": [
                {
                    "uuid": "11111111-2222-4333-8444-555555555552",
                    "type": "service",
                    "title": "Example service",
                    "description": "An example.",
                    "protocols": [
                        {
                            "uuid": "11111111-2222-4333-8444-555555555553",
                            "name": "https",
                            "port-ranges": [{"start": -1, "end": 443, "transport": "TCP"}],
                        }
                    ],
                }
            ],
        }
    }


def _witness_uuid_not_unique() -> Any:
    document = _catalog()
    document["catalog"]["uuid"] = _party_uuid(document)
    return document


def _witness_constraint_not_unique() -> Any:
    document = _catalog()
    controls = document["catalog"]["groups"][0]["controls"]
    controls[1]["id"] = controls[0]["id"]
    return document


def _witness_constraint_value_mismatch() -> Any:
    """``oscal-check-hash-length-SHA2-3-256`` declares ``^[0-9a-fA-F]{64}$``.

    Six hexadecimal characters under ``algorithm="SHA-256"`` is the shortest
    way to trip a ``matches`` constraint on a document that is otherwise clean.
    """
    document = _catalog()
    resource = document["catalog"]["back-matter"]["resources"][0]
    resource["rlinks"][0]["hashes"] = [{"algorithm": "SHA-256", "value": "abcdef"}]
    return document


def _witness_reference_unresolved() -> Any:
    document = _catalog()
    document["catalog"]["metadata"]["links"][0]["href"] = "#no-such-identifier"
    return document


def _witness_cardinality_warning() -> Any:
    document = _catalog()
    del document["catalog"]["back-matter"]["resources"][0]["rlinks"]
    return document


def _witness_oscal_version_differs() -> Any:
    document = _catalog()
    document["catalog"]["metadata"]["oscal-version"] = "1.1.2"
    return document


#: code -> (name, document, whether the profile's import is supplied).
WITNESSES: dict[str, tuple[str, Any, bool]] = {
    "REQUIRED_PROPERTY_MISSING": ("required-missing", _witness_required_property_missing(), False),
    "PROPERTY_UNDECLARED": ("undeclared", _witness_property_undeclared(), False),
    "TYPE_MISMATCH": ("mistyped", _witness_type_mismatch(), False),
    "ARRAY_TOO_SHORT": ("short-array", _witness_array_too_short(), False),
    "NO_SCHEMA_ALTERNATIVE": ("no-alternative", _witness_no_schema_alternative(), False),
    "SUBTREE_NOT_READ": ("unread-subtree", _witness_subtree_not_read(), False),
    "DATATYPE_MISMATCH": ("bad-datatype", _witness_datatype_mismatch(), False),
    "DATATYPE_BELOW_MINIMUM": ("below-minimum", _witness_datatype_below_minimum(), False),
    "UUID_NOT_UNIQUE": ("duplicate-uuid", _witness_uuid_not_unique(), False),
    "CONSTRAINT_NOT_UNIQUE": ("duplicate-control", _witness_constraint_not_unique(), False),
    "CONSTRAINT_CARDINALITY": ("no-rlink", _witness_cardinality_warning(), False),
    "CONSTRAINT_VALUE_MISMATCH": ("short-hash", _witness_constraint_value_mismatch(), False),
    "REFERENCE_UNRESOLVED": ("dangling", _witness_reference_unresolved(), False),
    "OSCAL_VERSION_DIFFERS": ("older-release", _witness_oscal_version_differs(), False),
    "PATTERN_NOT_CHECKED": ("clean-catalog", _catalog(), False),
    "CONSTRAINT_NOT_EVALUATED": ("clean-catalog", _catalog(), False),
    "IMPORT_NOT_SUPPLIED": ("profile-alone", _profile(), False),
    "REFERENCE_UNVERIFIABLE": ("profile-alone", _profile(), False),
    "IMPORT_RESOLVED": ("profile-resolved", _profile(), True),
}


def _run(tmp_path: Path, name: str, document: Any, resolved: bool) -> set[str]:
    path = write(tmp_path, f"{name}.json", document)
    resolve = [fixture_path("clean_catalog.json")] if resolved else None
    return {f.code for f in validate_file(path, resolve)}


@pytest.mark.parametrize("code", sorted(WITNESSES))
def test_every_rostered_code_is_produced_by_its_witness(code: str, tmp_path: Path) -> None:
    name, document, resolved = WITNESSES[code]
    assert code in _run(tmp_path, name, copy.deepcopy(document), resolved)


def test_import_ambiguous_needs_two_files_answering_to_one_name(tmp_path: Path) -> None:
    """The one witness that cannot be a single document.

    ``IMPORT_AMBIGUOUS`` is what the tool reports when two distinct supplied
    files answer to the name an import uses, so it takes two catalogs written
    to two directories under the one file name.
    """
    catalog = load_fixture("clean_catalog.json")
    other = copy.deepcopy(catalog)
    other["catalog"]["metadata"]["title"] = "A Different Catalog Of The Same Name"
    paths = []
    for index, payload in enumerate((catalog, other)):
        directory = tmp_path / f"publisher{index}"
        directory.mkdir()
        target = directory / "clean_catalog.json"
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        paths.append(target)
    profile = write(tmp_path, "p.json", _profile())
    assert "IMPORT_AMBIGUOUS" in {f.code for f in validate_file(profile, paths)}


def test_every_rostered_code_has_a_witness() -> None:
    """The assertion that makes the two above load-bearing.

    Without it, a code could be dropped from ``WITNESSES`` and the
    parametrized test would simply run one case fewer, in silence.
    """
    covered = set(WITNESSES) | {"IMPORT_AMBIGUOUS"}
    assert covered == set(ROSTER), sorted(set(ROSTER) - covered)
