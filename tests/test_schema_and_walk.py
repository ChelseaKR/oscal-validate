"""The vendored schema, and the walk that reads a document beside it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from oscal_validate.checks.references import IDENTITY_TITLES, REFERENCE_KINDS
from oscal_validate.document import DocumentError, escape, walk_document
from oscal_validate.schema import SchemaError, _one_or_many, load_schema, schema_release

MODELS = (
    "assessment-plan",
    "assessment-results",
    "catalog",
    "component-definition",
    "mapping-collection",
    "plan-of-action-and-milestones",
    "profile",
    "system-security-plan",
)


def test_every_oscal_model_root_is_indexed() -> None:
    assert load_schema().model_names() == MODELS


def test_the_datatypes_come_from_the_schema_not_from_here() -> None:
    datatypes = load_schema().datatypes
    uuid = datatypes["UUIDDatatype"]
    assert uuid.pattern is not None and uuid.pattern.startswith("^[0-9A-Fa-f]{8}-")
    assert "type 4" in uuid.description and "type 5" in uuid.description
    # The token pattern is the one Python cannot compile; the tool must know it.
    assert datatypes["TokenDatatype"].compiled is None
    assert datatypes["UUIDDatatype"].compiled is not None


def test_the_release_is_read_from_the_schema_id() -> None:
    assert schema_release() == "1.2.3"


def test_an_unsupported_ref_form_is_refused() -> None:
    with pytest.raises(SchemaError):
        load_schema().dereference("https://example.org/schema.json#/definitions/x")


def test_a_missing_definition_is_refused() -> None:
    with pytest.raises(SchemaError):
        load_schema().dereference("#/definitions/no-such-definition")


def test_json_pointer_tokens_are_escaped() -> None:
    assert escape("a/b~c") == "a~1b~0c"


def test_the_walk_records_a_datatype_for_every_scalar_it_reaches() -> None:
    document = json.loads(
        (Path(__file__).parent / "fixtures" / "clean_catalog.json").read_text(encoding="utf-8")
    )
    walked = walk_document(document, load_schema())
    assert walked.model == "catalog"
    uuids = [s for s in walked.scalars if s.datatype == "UUIDDatatype"]
    assert {s.pointer for s in uuids} >= {"/catalog/uuid"}
    assert all(s.datatype for s in walked.scalars), "a scalar with no declared datatype"


def test_a_document_nested_past_the_guard_is_refused() -> None:
    payload: Any = {"id": "deep", "title": "t"}
    for _ in range(120):
        payload = {"id": "g", "title": "t", "groups": [payload]}
    document = {
        "catalog": {
            "uuid": "f0d0a6cd-9e0e-4c2b-9b3e-0a3f2f7a1c11",
            "metadata": {
                "title": "t",
                "last-modified": "2026-08-14T00:00:00Z",
                "version": "1",
                "oscal-version": "1.2.3",
            },
            "groups": [payload],
        }
    }
    with pytest.raises(DocumentError, match="nests deeper"):
        walk_document(document, load_schema())


def test_every_identity_title_this_tool_relies_on_exists_in_the_schema() -> None:
    # The reference check keys off the schema's own titles. If a re-vendoring
    # renames one, the check would silently stop finding identifiers.
    titles = _titles_in_schema()
    assert titles >= IDENTITY_TITLES, IDENTITY_TITLES - titles


def test_every_reference_title_this_tool_relies_on_exists_in_the_schema() -> None:
    titles = _titles_in_schema()
    assert set(REFERENCE_KINDS) <= titles, set(REFERENCE_KINDS) - titles


def test_every_reference_kind_points_at_a_title_that_declares_identifiers() -> None:
    for kind in REFERENCE_KINDS.values():
        assert kind.targets <= IDENTITY_TITLES, kind.title


def _titles_in_schema() -> set[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            title = node.get("title")
            if isinstance(title, str):
                found.add(title)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(load_schema().raw)
    return found


def _union_nodes(node: Any, path: str) -> list[tuple[str, dict[str, Any]]]:
    """Every ``allOf``/``anyOf`` node in the vendored schema, with its path."""
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        if node.get("allOf") or node.get("anyOf"):
            found.append((path, node))
        for key, value in node.items():
            found.extend(_union_nodes(value, f"{path}/{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_union_nodes(value, f"{path}/{index}"))
    return found


def test_one_mapping_or_many_is_the_only_place_the_schema_writes_that_shape() -> None:
    """The size of the eighth model's blocker, read off the vendored file.

    ADR-0007 turns on this count. Every other repeatable assembly in OSCAL
    1.2.3 is a plain array, because every other ``group-as`` in the vendored
    metaschema modules carries ``in-json="ARRAY"``. If a later release writes
    the shape somewhere else, this test says so rather than letting the ADR go
    on describing a schema that has moved.
    """
    schema = load_schema()
    matched = [
        path
        for path, node in _union_nodes(schema.raw["definitions"], "#/definitions")
        if _one_or_many(node) is not None
    ]
    assert matched == [
        "#/definitions/oscal-complete-oscal-mapping:mapping-collection/properties/mappings"
    ]


def test_no_document_shape_in_the_vendored_schema_is_left_unresolved() -> None:
    """Nothing reachable from a model root is declined by the resolver now.

    The three definitions the resolver still declines when handed their own
    bodies are ``EmailAddressDatatype``, ``NonNegativeIntegerDatatype`` and
    ``PositiveIntegerDatatype``, and the walk never hands it those: a ``$ref``
    to a name ending in ``Datatype`` resolves to the datatype itself. So the
    count of shapes a document can actually land on and have declined is zero,
    and this test is what would notice it stopping being zero.
    """
    schema = load_schema()
    declined = sorted(
        path
        for path, node in _union_nodes(schema.raw["definitions"], "#/definitions")
        if schema.resolve(node).unresolved is not None
    )
    assert declined == [
        "#/definitions/EmailAddressDatatype",
        "#/definitions/NonNegativeIntegerDatatype",
        "#/definitions/PositiveIntegerDatatype",
    ]
    for name in declined:
        assert schema.datatypes.get(name.rsplit("/", 1)[-1]) is not None, (
            "a declined node that is not a datatype would be reachable by the walk"
        )


#: The shape ADR-0007 resolves, written the way the vendored schema writes it.
_ONE = {"$ref": "#/definitions/x"}
_MANY = {"type": "array", "minItems": 1, "items": {"$ref": "#/definitions/x"}}


@pytest.mark.parametrize(
    ("node", "why"),
    [
        ({"anyOf": [_ONE, _MANY, _ONE]}, "three branches are not this shape"),
        ({"anyOf": [_ONE, "not an object"]}, "a branch that is not an object"),
        ({"anyOf": [_ONE, {"$ref": "#/definitions/x"}]}, "neither branch is an array"),
        ({"anyOf": [_ONE, {"type": "array"}]}, "the array declares no item shape"),
        (
            {"anyOf": [_ONE, {"type": "array", "items": {"type": "string"}}]},
            "the array's items are not a bare $ref",
        ),
        (
            {
                "anyOf": [
                    _ONE,
                    {"type": "array", "items": {"$ref": "#/definitions/other"}},
                ]
            },
            "two different targets are a real choice between alternatives",
        ),
        ({"anyOf": [{"properties": {}}, _MANY]}, "the singleton branch is not a bare $ref"),
    ],
)
def test_anything_that_is_not_one_x_or_an_array_of_x_is_declined(
    node: dict[str, Any], why: str
) -> None:
    """The guard the decision rests on: a real choice is still declined.

    ADR-0007 resolves one shape because in that shape the schema decides which
    branch applies and this tool chooses nothing. Every near miss below leaves
    a choice to be made, and a walker that made it would be guessing at a shape
    NIST did not state.
    """
    assert _one_or_many(node) is None, why


def test_both_orders_of_the_two_branches_resolve_the_same() -> None:
    """The schema writes the singleton first; nothing depends on that."""
    assert _one_or_many({"anyOf": [_ONE, _MANY]}) == (_ONE, _MANY)
    assert _one_or_many({"anyOf": [_MANY, _ONE]}) == (_ONE, _MANY)
