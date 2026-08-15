"""Break the gate on purpose before trusting it.

Discipline these tests encode: a gate is only trusted after deliberately
corrupting a known-good document and confirming the gate catches the
corruption. Each test starts from a fixture proven clean first, breaks exactly
one thing, and asserts the specific catch.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from oscal_validate import Severity, validate_file

from .conftest import fixture_path, load_fixture, write


def _codes(path: Path, resolve: list[Path] | None = None) -> set[str]:
    return {f.code for f in validate_file(path, resolve)}


def _errors(path: Path, resolve: list[Path] | None = None) -> set[str]:
    return {f.code for f in validate_file(path, resolve) if f.severity is Severity.ERROR}


@pytest.fixture
def clean_catalog() -> Any:
    findings = validate_file(fixture_path("clean_catalog.json"))
    assert not [f for f in findings if f.severity is Severity.ERROR], (
        "gate tests require a proven-clean baseline"
    )
    return copy.deepcopy(load_fixture("clean_catalog.json"))


def test_removing_a_required_property_is_caught(tmp_path: Path, clean_catalog: Any) -> None:
    del clean_catalog["catalog"]["metadata"]["last-modified"]
    assert "REQUIRED_PROPERTY_MISSING" in _errors(write(tmp_path, "c.json", clean_catalog))


def test_a_property_the_schema_forbids_is_caught(tmp_path: Path, clean_catalog: Any) -> None:
    clean_catalog["catalog"]["metadata"]["invented-property"] = "hello"
    assert "PROPERTY_UNDECLARED" in _errors(write(tmp_path, "c.json", clean_catalog))


def test_a_malformed_uuid_is_caught(tmp_path: Path, clean_catalog: Any) -> None:
    clean_catalog["catalog"]["uuid"] = "not-a-uuid"
    assert "DATATYPE_MISMATCH" in _errors(write(tmp_path, "c.json", clean_catalog))


def test_a_uuid_v1_is_caught_because_oscal_requires_v4_or_v5(
    tmp_path: Path, clean_catalog: Any
) -> None:
    # OSCAL's UUIDDatatype pattern pins the version nibble to 4 or 5.
    clean_catalog["catalog"]["uuid"] = "f0d0a6cd-9e0e-1c2b-9b3e-0a3f2f7a1c11"
    assert "DATATYPE_MISMATCH" in _errors(write(tmp_path, "c.json", clean_catalog))


def test_a_timestamp_without_a_timezone_is_caught(tmp_path: Path, clean_catalog: Any) -> None:
    clean_catalog["catalog"]["metadata"]["last-modified"] = "2026-08-14T00:00:00"
    assert "DATATYPE_MISMATCH" in _errors(write(tmp_path, "c.json", clean_catalog))


def test_a_wrong_json_type_is_caught(tmp_path: Path, clean_catalog: Any) -> None:
    clean_catalog["catalog"]["metadata"]["title"] = {"not": "a string"}
    assert "TYPE_MISMATCH" in _errors(write(tmp_path, "c.json", clean_catalog))


def test_a_duplicate_uuid_is_caught(tmp_path: Path, clean_catalog: Any) -> None:
    clean_catalog["catalog"]["metadata"]["parties"][0]["uuid"] = clean_catalog["catalog"]["uuid"]
    assert "UUID_NOT_UNIQUE" in _errors(write(tmp_path, "c.json", clean_catalog))


def test_a_duplicate_control_id_is_caught(tmp_path: Path, clean_catalog: Any) -> None:
    controls = clean_catalog["catalog"]["groups"][0]["controls"]
    controls[1]["id"] = controls[0]["id"]
    assert "CONSTRAINT_NOT_UNIQUE" in _errors(write(tmp_path, "c.json", clean_catalog))


def test_a_role_id_that_names_no_role_is_caught(tmp_path: Path, clean_catalog: Any) -> None:
    clean_catalog["catalog"]["metadata"]["responsible-parties"][0]["role-id"] = "no-such-role"
    assert "REFERENCE_UNRESOLVED" in _errors(write(tmp_path, "c.json", clean_catalog))


def test_a_party_uuid_that_names_no_party_is_caught(tmp_path: Path, clean_catalog: Any) -> None:
    clean_catalog["catalog"]["metadata"]["responsible-parties"][0]["party-uuids"] = [
        "11111111-2222-4333-8444-555555555555"
    ]
    assert "REFERENCE_UNRESOLVED" in _errors(write(tmp_path, "c.json", clean_catalog))


def test_a_dangling_back_matter_fragment_is_caught(tmp_path: Path, clean_catalog: Any) -> None:
    clean_catalog["catalog"]["metadata"]["links"][0]["href"] = (
        "#99999999-8888-4777-8666-555555555555"
    )
    assert "REFERENCE_UNRESOLVED" in _errors(write(tmp_path, "c.json", clean_catalog))


def test_a_profile_control_reference_that_misses_is_caught_only_with_the_catalog(
    tmp_path: Path,
) -> None:
    profile = copy.deepcopy(load_fixture("clean_profile.json"))
    profile["profile"]["imports"][0]["include-controls"][0]["with-ids"] = ["ex-1", "ex-99"]
    path = write(tmp_path, "clean_profile.json", profile)
    catalog = fixture_path("clean_catalog.json")

    # Without the catalog the answer is unknown, and unknown is not a failure.
    assert "REFERENCE_UNRESOLVED" not in _errors(path)
    assert "REFERENCE_UNVERIFIABLE" in _codes(path)

    # With it, the effective data model is complete and the miss is an error.
    assert "REFERENCE_UNRESOLVED" in _errors(path, [catalog])


def test_an_object_no_schema_alternative_accepts_is_caught(
    tmp_path: Path, clean_catalog: Any
) -> None:
    # A group may hold controls or groups, never both.
    clean_catalog["catalog"]["groups"][0]["groups"] = [{"id": "sub", "title": "Sub"}]
    assert "NO_SCHEMA_ALTERNATIVE" in _errors(write(tmp_path, "c.json", clean_catalog))
