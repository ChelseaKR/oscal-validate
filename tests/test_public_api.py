"""``oscal_validate``'s public surface, pinned so that changing it is deliberate.

``evals/`` and ``tools/`` already import this package, and issue #72 makes
that a promise rather than an accident. The pins below are not busywork: a
signature here is what another repository writes its call against, and the
failure mode of an unpinned surface is a caller that breaks on an upgrade with
nothing in the CHANGELOG to explain it.

So the exported names, their kinds, and their exact signatures are written out
here. Changing one turns this file red on purpose: edit it in the same commit
that changes the API, and say so in the CHANGELOG under ``Changed`` --
``docs/API.md`` states which changes require a major release.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
from pathlib import Path

import pytest

import oscal_validate
from oscal_validate import Acknowledgement, Finding, Position, Rule, Severity

ROOT = Path(__file__).resolve().parent.parent
API_DOC = ROOT / "docs" / "API.md"
CHANGELOG = ROOT / "CHANGELOG.md"

#: Every public name, and the exact signature it is promised to keep. A
#: callable's signature is compared as ``str(inspect.signature(...))``; a
#: non-callable's entry is None and only its presence and type are pinned.
PUBLIC: dict[str, str | None] = {
    "REPORT_SCHEMA_VERSION": None,
    "Acknowledgement": None,
    "Finding": None,
    "Position": None,
    "Rule": None,
    "Severity": None,
    "__version__": None,
    "build_session": (
        "(document: 'Path', resolve: 'list[Path] | None' = None, *, suggest: 'bool' = False,"
        " locations: 'bool' = False) -> 'Session'"
    ),
    "read_report_schema": "() -> 'str'",
    "validate": "(session: 'Session') -> 'list[Finding]'",
    "validate_file": (
        "(document: 'Path', resolve: 'list[Path] | None' = None, *, suggest: 'bool' = False,"
        " locations: 'bool' = False) -> 'list[Finding]'"
    ),
}

#: The fields of ``Finding``, in order, with their declared types. A field
#: removed or renamed breaks every consumer; a field added without a default
#: breaks every constructor call.
FINDING_FIELDS = [
    ("code", "str"),
    ("severity", "Severity"),
    ("location", "str"),
    ("prop", "str"),
    ("value", "str"),
    ("message", "str"),
    ("rule", "Rule"),
    ("suggestions", "tuple[Suggestion, ...]"),
    ("acknowledged", "Acknowledgement | None"),
    ("position", "Position | None"),
]

#: ``Acknowledgement``'s fields. It is public because ``Finding.acknowledged``
#: is typed with it: a public field whose type a caller cannot import is not a
#: promise anyone can write against.
ACKNOWLEDGEMENT_FIELDS = [("reason", "str"), ("acknowledged_on", "str")]

RULE_FIELDS = [("citation", "str"), ("url", "str"), ("retrieved", "str")]

#: ``Position``'s fields. Public for the same reason ``Acknowledgement`` is:
#: ``Finding.position`` is typed with it.
POSITION_FIELDS = [("file", "str"), ("line", "int"), ("column", "int")]


def test_all_is_exactly_the_documented_surface() -> None:
    assert sorted(oscal_validate.__all__) == sorted(PUBLIC)


def test_every_public_name_is_importable() -> None:
    for name in PUBLIC:
        assert hasattr(oscal_validate, name), name


def test_every_public_signature_is_the_one_that_was_promised() -> None:
    for name, expected in PUBLIC.items():
        if expected is None:
            continue
        actual = str(inspect.signature(getattr(oscal_validate, name)))
        assert actual == expected, f"{name}{actual} is not the promised {name}{expected}"


def test_finding_and_rule_keep_their_fields() -> None:
    assert [(f.name, f.type) for f in dataclasses.fields(Finding)] == FINDING_FIELDS
    assert [(f.name, f.type) for f in dataclasses.fields(Rule)] == RULE_FIELDS
    assert all(field.default is dataclasses.MISSING for field in dataclasses.fields(Rule))


def test_only_the_three_opt_in_fields_are_optional_on_a_finding() -> None:
    """Every other field is required, so a Finding cannot be built short of
    one and have the gap read as an empty string.

    All three optional fields are opt-in output: ``suggestions`` needs
    ``--suggest``, ``acknowledged`` needs ``--baseline`` and ``position``
    needs ``--locations``. Their defaults are the *absence* of a claim, not a
    neutral value -- a Finding with ``acknowledged=None`` is one nothing
    acknowledged, and it gates; a Finding with ``position=None`` is one this
    run has no source position for, and the report says so in words rather
    than printing a line 0."""
    optional = [
        field.name
        for field in dataclasses.fields(Finding)
        if field.default is not dataclasses.MISSING
        or field.default_factory is not dataclasses.MISSING
    ]
    assert optional == ["suggestions", "acknowledged", "position"]


def test_a_position_keeps_its_fields_and_is_frozen() -> None:
    assert [(f.name, f.type) for f in dataclasses.fields(Position)] == POSITION_FIELDS
    position = Position(file="doc.json", line=1, column=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        position.line = 2  # type: ignore[misc]


def test_an_acknowledgement_keeps_its_fields_and_is_frozen() -> None:
    assert [(f.name, f.type) for f in dataclasses.fields(Acknowledgement)] == (
        ACKNOWLEDGEMENT_FIELDS
    )
    acknowledgement = Acknowledgement(reason="r", acknowledged_on="2026-01-01")
    with pytest.raises(dataclasses.FrozenInstanceError):
        acknowledgement.reason = "changed"  # type: ignore[misc]


def test_only_an_unacknowledged_error_gates() -> None:
    """``Finding.gates`` is the one place the exit code is decided, so it is
    part of the promise rather than an implementation detail."""
    rule = Rule(citation="c", url="https://example.invalid/", retrieved="2026-01-01")
    error = Finding("CODE", Severity.ERROR, "/catalog", "p", "v", "m", rule)
    assert error.gates is True
    assert (
        dataclasses.replace(error, acknowledged=Acknowledgement("because", "2026-01-01")).gates
        is False
    )
    for severity in (Severity.WARNING, Severity.INFO, Severity.UNVERIFIABLE):
        assert dataclasses.replace(error, severity=severity).gates is False


def test_finding_and_rule_are_frozen() -> None:
    """A consumer holding a Finding must not be able to change it under the
    code that produced it."""
    rule = Rule(citation="c", url="https://example.invalid/", retrieved="2026-01-01")
    finding = Finding("CODE", Severity.ERROR, "/catalog", "prop", "value", "message", rule)
    for instance, field_name in ((rule, "citation"), (finding, "severity")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, field_name, "changed")


def test_severity_members_are_the_four_the_report_declares() -> None:
    assert [s.value for s in Severity] == ["ERROR", "WARNING", "INFO", "UNVERIFIABLE"]


def test_the_api_document_names_every_public_symbol() -> None:
    """A promise nobody can read is not a promise."""
    documented = API_DOC.read_text(encoding="utf-8")
    for name in PUBLIC:
        assert f"`{name}`" in documented, f"docs/API.md does not mention {name}"


#: One row of docs/API.md's library table whose second cell is a signature.
#: Types and constants carry prose there ("frozen dataclass", `str`), so only a
#: cell that opens with ``(`` is a signature, and only those rows are read.
_SIGNATURE_ROW = re.compile(
    r"^\| `(?P<name>[A-Za-z_]+)` \| `(?P<signature>\([^`]*)` \|", re.MULTILINE
)


def _documented_signatures() -> dict[str, str]:
    documented = API_DOC.read_text(encoding="utf-8")
    return {
        row["name"]: row["signature"].replace("\\|", "|")
        for row in _SIGNATURE_ROW.finditer(documented)
    }


def test_the_api_document_states_every_signature_the_code_has() -> None:
    """A name is not a signature, and the document is where a caller reads one.

    ``test_the_api_document_names_every_public_symbol`` checks that each name is
    *mentioned*. That let two rows go stale: #95 added ``locations`` to
    ``build_session`` and ``validate_file``, the pins in ``PUBLIC`` moved with
    it, and docs/API.md went on publishing the old signatures with the suite
    green. So each function's row is compared with ``inspect.signature``
    itself -- not with ``PUBLIC``, which is one more copy -- in both
    directions: a public function with no row fails, and so does a row for a
    function that is not public.
    """
    functions = {
        name for name in oscal_validate.__all__ if inspect.isfunction(getattr(oscal_validate, name))
    }
    documented = _documented_signatures()
    assert functions, "no public function found; everything below would be vacuous"
    assert set(documented) == functions, (
        f"rows without a public function: {sorted(set(documented) - functions)}; "
        f"public functions without a row: {sorted(functions - set(documented))}"
    )
    stale = {
        name: (
            documented[name],
            str(inspect.signature(getattr(oscal_validate, name))).replace("'", ""),
        )
        for name in sorted(functions)
        if documented[name]
        != str(inspect.signature(getattr(oscal_validate, name))).replace("'", "")
    }
    assert not stale, "docs/API.md publishes a signature the code does not have: " + "; ".join(
        f"{name} documented {written} but is {actual}" for name, (written, actual) in stale.items()
    )


def test_the_api_document_states_the_stability_rule() -> None:
    documented = API_DOC.read_text(encoding="utf-8")
    assert "Semantic Versioning" in documented
    assert "report_schema_version" in documented


def test_the_changelog_records_this_surface_being_named() -> None:
    """The pin above is only half of it: the surface has to be announced.

    This is the mechanical half of "no signature change without a CHANGELOG
    entry" -- it checks the entry that named the API exists at all, so the
    document and the promise cannot land without one."""
    assert "docs/API.md" in CHANGELOG.read_text(encoding="utf-8")
