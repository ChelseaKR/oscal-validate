"""The vendored schema, and the walk that reads a document beside it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from oscal_validate.checks.references import IDENTITY_TITLES, REFERENCE_KINDS
from oscal_validate.document import DocumentError, escape, walk_document
from oscal_validate.schema import SchemaError, load_schema, schema_release

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
