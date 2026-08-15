"""The constraint layer, parsed out of the vendored metaschema files.

These tests pin two things: that the Metapath subset is exactly the subset it
claims to be, and that the coverage numbers the tool reports are the numbers
the vendored files actually contain. A coverage claim that drifts from its
source is worse than no claim.
"""

from __future__ import annotations

from collections import Counter

import pytest

from oscal_validate.metaschema import (
    EVALUATED_KINDS,
    UNEVALUATED_KINDS,
    KeyField,
    Step,
    key_values,
    load_metaschema,
    parse_target,
    select,
)

#: The published constraint inventory of OSCAL 1.2.3, and what this tool runs.
#: Both halves are asserted so that a re-vendoring shows a reviewable diff.
PUBLISHED = {
    "allowed-values": 200,
    "expect": 12,
    "has-cardinality": 11,
    "index": 20,
    "index-has-key": 24,
    "is-unique": 48,
    "matches": 25,
}
EVALUATED = {"has-cardinality": 5, "index": 15, "index-has-key": 10, "is-unique": 48}


def test_the_published_constraint_inventory_is_what_we_say_it_is() -> None:
    metaschema = load_metaschema()
    assert Counter(c.kind for c in metaschema.constraints) == Counter(PUBLISHED)


def test_the_evaluated_subset_is_what_we_say_it_is() -> None:
    metaschema = load_metaschema()
    assert Counter(c.kind for c in metaschema.evaluated()) == Counter(EVALUATED)
    assert len(metaschema.evaluated()) == 78
    assert len(metaschema.constraints) == 340


def test_every_skipped_constraint_says_why() -> None:
    for constraint in load_metaschema().skipped():
        assert constraint.skipped, constraint.identifier


def test_no_constraint_is_evaluated_without_a_parsed_target() -> None:
    for constraint in load_metaschema().evaluated():
        assert constraint.kind in EVALUATED_KINDS
        assert constraint.steps is not None
        assert constraint.context


def test_the_unevaluated_kinds_are_declared_with_reasons() -> None:
    for kind, reason in UNEVALUATED_KINDS.items():
        assert kind in PUBLISHED
        assert reason


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        (".", ()),
        ("role", (Step(("role",), False),)),
        ("//control", (Step(("control",), True),)),
        (".//prop", (Step(("prop",), True),)),
        ("//(control|group|part)", (Step(("control", "group", "part"), True),)),
        ("rlink|base64", (Step(("rlink", "base64"), False),)),
        ("component/link", (Step(("component",), False), Step(("link",), False))),
    ],
)
def test_the_supported_metapath_subset_parses(expression: str, expected: tuple[Step, ...]) -> None:
    assert parse_target(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "component[@type='service']",
        "link[@rel='diagram' and starts-with(@href,'#')]",
        "doc(system-implementation/leveraged-authorization/link/@href)/system-security-plan",
        "//(control|group",
        "//a/b",
        "child::control",
    ],
)
def test_expressions_outside_the_subset_are_refused_rather_than_guessed(expression: str) -> None:
    assert parse_target(expression) is None


def test_select_walks_json_by_the_names_the_metaschema_groups_them_under() -> None:
    metaschema = load_metaschema()
    document = {
        "catalog": {
            "groups": [{"id": "g", "controls": [{"id": "c1"}, {"id": "c2"}]}],
            "controls": [{"id": "c3"}],
        }
    }
    found = select(document, "", (Step(("control",), True),), metaschema)
    assert sorted(located.value["id"] for located in found) == ["c1", "c2", "c3"]
    assert "/catalog/groups/0/controls/0" in {located.pointer for located in found}


def test_key_fields_read_flags_children_and_patterns() -> None:
    metaschema = load_metaschema()
    node = {"role-id": "admin", "party-uuids": ["a", "b"], "href": "#abc123"}
    assert key_values(node, KeyField("@role-id", None), metaschema) == ["admin"]
    assert key_values(node, KeyField("party-uuid", None), metaschema) == ["a", "b"]
    assert key_values(node, KeyField("@href", "#(.*)"), metaschema) == ["abc123"]
    assert key_values(node, KeyField("@missing", None), metaschema) is None


def test_a_pattern_that_does_not_match_selects_nothing() -> None:
    metaschema = load_metaschema()
    assert (
        key_values({"href": "https://example.org"}, KeyField("@href", "#(.*)"), metaschema) is None
    )
