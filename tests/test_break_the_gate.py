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


@pytest.fixture
def clean_mapping() -> Any:
    findings = validate_file(fixture_path("clean_mapping_collection.json"))
    assert not [f for f in findings if f.severity is Severity.ERROR], (
        "gate tests require a proven-clean baseline"
    )
    assert "SUBTREE_NOT_READ" not in {f.code for f in findings}, (
        "a mapping whose substance was not read is not a proven-clean baseline"
    )
    return copy.deepcopy(load_fixture("clean_mapping_collection.json"))


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


def test_a_member_of_organizations_that_names_no_organization_is_caught(
    tmp_path: Path, clean_catalog: Any
) -> None:
    """A gate that only exists since predicate targets parse (ADR-0004).

    NIST builds ``index-metadata-party-organizations-uuid`` with an ``index``
    constraint whose target is ``party[@type='organization']``. Until the
    bounded predicate grammar, that index was never populated and every lookup
    into it was UNVERIFIABLE. Now it is built, so a person claiming membership
    of an organization the document does not declare is a caught ERROR -- and
    membership of the organization it does declare stays clean.
    """
    organization = clean_catalog["catalog"]["metadata"]["parties"][0]
    person = {
        "uuid": "5c2b0d18-2b7a-4f6e-9a0e-2c1d3e4f5a60",
        "type": "person",
        "name": "Example Person",
        "member-of-organizations": [organization["uuid"]],
    }
    clean_catalog["catalog"]["metadata"]["parties"].append(person)
    path = write(tmp_path, "resolves.json", clean_catalog)
    findings = validate_file(path)
    assert "REFERENCE_UNRESOLVED" not in {f.code for f in findings}
    assert not [f for f in findings if "index-metadata-party-organizations-uuid" in f.message], (
        "a membership the index resolves must produce no finding at all"
    )

    person["member-of-organizations"] = ["11111111-2222-4333-8444-555555555555"]
    dangling = _errors(write(tmp_path, "dangles.json", clean_catalog))
    assert "REFERENCE_UNRESOLVED" in dangling, (
        "a membership naming no declared organization must be caught now that "
        "the party[@type='organization'] index is built"
    )


#: A UUID no fixture declares, so a reference to it resolves to nothing.
DANGLING = "00000000-0000-4000-8000-000000000000"


def test_a_lookup_into_an_index_that_was_never_built_is_never_an_error(tmp_path: Path) -> None:
    """A skipped constraint accuses nobody.

    One published index is still never built: ``by-component-uuid``,
    whose target dereferences a second document through ``doc()``. The
    ``index-has-key`` on ``link[@rel='provided-by']`` that reads it *is*
    evaluated, and a lookup into an index that was never populated misses
    every key. Reporting the miss as a failure would report a rule this tool
    did not evaluate as a defect in someone's document, so it is UNVERIFIABLE
    and names the index.
    """
    ssp = {
        "system-security-plan": {
            "uuid": "7b1d6c8a-4a5e-4b3c-8d2f-1e0a9b8c7d61",
            "metadata": {
                "title": "Gate fixture",
                "last-modified": "2026-08-19T00:00:00Z",
                "version": "1",
                "oscal-version": "1.2.3",
            },
            "import-profile": {"href": "#11111111-2222-4333-8444-555555555555"},
            "control-implementation": {
                "description": "One by-component whose provided-by cannot be looked up.",
                "implemented-requirements": [
                    {
                        "uuid": "9c8b7a6d-5e4f-4321-9876-0a1b2c3d4e5f",
                        "control-id": "ac-1",
                        "by-components": [
                            {
                                "component-uuid": "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
                                "uuid": "1f2e3d4c-5b6a-4978-8695-a4b3c2d1e0f9",
                                "description": "x",
                                "links": [{"href": "#dead", "rel": "provided-by"}],
                            }
                        ],
                    }
                ],
            },
        }
    }
    path = write(tmp_path, "ssp.json", ssp)
    findings = validate_file(path)
    unsettled = [
        f
        for f in findings
        if f.code == "REFERENCE_UNVERIFIABLE" and "by-component-uuid" in f.message
    ]
    assert unsettled, "the unbuilt index must be named, not silently passed"
    assert all(f.severity is Severity.UNVERIFIABLE for f in unsettled)
    assert not [
        f for f in findings if f.code == "REFERENCE_UNRESOLVED" and "by-component-uuid" in f.message
    ]


def test_a_settled_report_never_replaces_an_unsettled_one_about_the_same_reference(
    tmp_path: Path,
) -> None:
    """The same guarantee as the test above, at the point the reports are merged.

    The document here is the one difference that matters: its import-profile
    names a real file, and that file is supplied, so the effective data model
    is complete and check 4's prose rule settles the ``provided-by`` href as
    resolving to nothing. The constraint layer cannot settle it, because the
    ``by-component-uuid`` index its ``index-has-key`` reads is never built.

    One href, two reports, opposite verdicts. Deduplicating them on a
    normalized key without deciding the order lets the ERROR replace the
    UNVERIFIABLE, and the unbuilt index stops being named at all: the same
    silence the test above forbids, arriving through the merge instead of
    through the check. The unsettled report is the one that survives, and it
    keeps citing the rule that explains why nothing here can settle it.
    """
    ssp = {
        "system-security-plan": {
            "uuid": "7b1d6c8a-4a5e-4b3c-8d2f-1e0a9b8c7d61",
            "metadata": {
                "title": "Gate fixture",
                "last-modified": "2026-08-19T00:00:00Z",
                "version": "1",
                "oscal-version": "1.2.3",
            },
            "import-profile": {"href": "profile.json"},
            "control-implementation": {
                "description": "One by-component whose provided-by cannot be looked up.",
                "implemented-requirements": [
                    {
                        "uuid": "9c8b7a6d-5e4f-4321-9876-0a1b2c3d4e5f",
                        "control-id": "ac-1",
                        "by-components": [
                            {
                                "component-uuid": "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
                                "uuid": "1f2e3d4c-5b6a-4978-8695-a4b3c2d1e0f9",
                                "description": "x",
                                "links": [{"href": f"#{DANGLING}", "rel": "provided-by"}],
                            }
                        ],
                    }
                ],
            },
        }
    }
    profile = {
        "profile": {
            "uuid": "11111111-2222-4333-8444-555555555555",
            "metadata": {
                "title": "Minimal profile",
                "last-modified": "2026-08-19T00:00:00Z",
                "version": "1",
                "oscal-version": "1.2.3",
            },
            "imports": [],
        }
    }
    document = write(tmp_path, "ssp.json", ssp)
    supplied = write(tmp_path, "profile.json", profile)

    findings = validate_file(document, [supplied])
    assert not [f for f in findings if f.code == "IMPORT_UNRESOLVED"], (
        "this case only exists when the effective data model is complete"
    )
    about = [f for f in findings if f.code.startswith("REFERENCE_") and DANGLING in f.value]
    assert len(about) == 1, (
        f"one href must not produce two verdicts; got {[(f.code, f.location) for f in about]}"
    )
    assert about[0].code == "REFERENCE_UNVERIFIABLE"
    assert about[0].severity is Severity.UNVERIFIABLE
    assert "by-component-uuid" in about[0].message, "the unbuilt index must still be named"
    assert "NIST OSCAL constraint" not in about[0].rule.citation, (
        "a constraint this tool did not evaluate is not the authority for the finding "
        "that it could not evaluate it"
    )
    assert "oscal-validate policy" in about[0].rule.citation, (
        "the authority is this tool's own limit; every import here was supplied, so a "
        "citation about documents that were not supplied would send the reader nowhere"
    )


def test_an_object_no_schema_alternative_accepts_is_caught(
    tmp_path: Path, clean_catalog: Any
) -> None:
    # A group may hold controls or groups, never both.
    clean_catalog["catalog"]["groups"][0]["groups"] = [{"id": "sub", "title": "Sub"}]
    assert "NO_SCHEMA_ALTERNATIVE" in _errors(write(tmp_path, "c.json", clean_catalog))


#: Every JSON scalar. A whole assembly replaced by any one of them is the same
#: defect, and the walk reaches all four through one path.
SCALARS = [None, "a string", 42, True]


@pytest.mark.parametrize("scalar", SCALARS)
def test_an_assembly_replaced_by_a_scalar_is_caught(
    tmp_path: Path, clean_catalog: Any, scalar: Any
) -> None:
    """The gate that could not fail: a scalar standing in for a whole assembly.

    ``metadata`` is required, and it carries four required properties of its
    own. Replacing it with a scalar removes all of that from the document, and
    nothing below the substitution is reachable to be checked. Before this was
    fixed the walk filed the scalar as an untyped value and moved on, so the
    report was 0 ERROR and the exit code 0: the same verdict as the clean
    fixture this test's own baseline proves.
    """
    clean_catalog["catalog"]["metadata"] = scalar
    assert "TYPE_MISMATCH" in _errors(write(tmp_path, "c.json", clean_catalog))


@pytest.mark.parametrize("scalar", SCALARS)
def test_a_model_root_replaced_by_a_scalar_is_caught(tmp_path: Path, scalar: Any) -> None:
    """The same defect at the top: a document with no body at all.

    ``{"catalog": null}`` names a model and then supplies nothing. It used to
    exit 0 with no ERROR finding, which is a validator reporting a pass over a
    document it never read.
    """
    findings = validate_file(write(tmp_path, "c.json", {"catalog": scalar}))
    assert "TYPE_MISMATCH" in {f.code for f in findings if f.severity is Severity.ERROR}


def test_a_value_below_the_schemas_declared_minimum_is_caught(tmp_path: Path) -> None:
    """A rule the schema states as a bound rather than a pattern.

    ``NonNegativeIntegerDatatype`` carries ``"minimum": 0`` in an ``allOf``
    beside a ``$ref`` to ``IntegerDatatype``. The datatype check keyed off
    ``pattern`` alone, so both facets were dropped: a port range of ``-1`` read
    byte for byte like one of ``443``.
    """
    document = _component_definition(start=-1, end=443)
    assert "DATATYPE_BELOW_MINIMUM" in _errors(write(tmp_path, "cd.json", document))


def test_a_fractional_value_in_an_integer_datatype_is_caught(tmp_path: Path) -> None:
    """The narrowing an ``allOf`` states, which reading one branch loses.

    ``PositiveIntegerDatatype`` and ``NonNegativeIntegerDatatype`` are each a
    ``$ref`` to ``IntegerDatatype`` beside a branch declaring ``"number"``. An
    ``allOf`` requires both at once, so the conjunction is ``integer``.
    """
    document = _component_definition(start=443, end=99.5)
    assert "TYPE_MISMATCH" in _errors(write(tmp_path, "cd.json", document))


def test_a_valid_port_range_stays_clean(tmp_path: Path) -> None:
    """The other direction, so the two tests above cannot pass by over-reporting."""
    document = _component_definition(start=443, end=443)
    assert not _errors(write(tmp_path, "cd.json", document))


def test_an_array_the_schema_requires_items_in_is_caught_when_empty(
    tmp_path: Path, clean_catalog: Any
) -> None:
    """``minItems`` is declared 409 times in the schema and was evaluated zero times.

    OSCAL declares ``"minItems": 1`` on every array it defines. An array that is
    present and empty is not the same document as one that omits the property,
    and only the second conforms.
    """
    clean_catalog["catalog"]["groups"][0]["controls"] = []
    assert "ARRAY_TOO_SHORT" in _errors(write(tmp_path, "c.json", clean_catalog))


# -- the eighth model ---------------------------------------------------------
#
# Until the walk resolved "one mapping or an array of mappings", every one of
# these seeded corruptions went uncaught: /mapping-collection/mappings was
# reported SUBTREE_NOT_READ and nothing below it was read by any rule. The
# model had no gate to break. See ADR-0007 and issue #7.


def _maps(mapping_collection: Any) -> Any:
    return mapping_collection["mapping-collection"]["mappings"][0]["maps"][0]


def test_a_required_property_removed_inside_a_mapping_is_caught(
    tmp_path: Path, clean_mapping: Any
) -> None:
    del _maps(clean_mapping)["relationship"]
    assert "REQUIRED_PROPERTY_MISSING" in _errors(write(tmp_path, "m.json", clean_mapping))


def test_a_property_the_schema_forbids_inside_a_mapping_is_caught(
    tmp_path: Path, clean_mapping: Any
) -> None:
    """The real defect this shape hides: an underscore where OSCAL writes a hyphen.

    ``mapping-item`` declares ``id-ref`` and sets ``additionalProperties`` to
    false, so ``id_ref`` is both an undeclared property and a required one
    missing. Two of the seven published mapping collections carry it.
    """
    source = _maps(clean_mapping)["sources"][0]
    source["id_ref"] = source.pop("id-ref")
    codes = _errors(write(tmp_path, "m.json", clean_mapping))
    assert "PROPERTY_UNDECLARED" in codes
    assert "REQUIRED_PROPERTY_MISSING" in codes


def test_a_dangling_resource_reference_inside_a_mapping_is_caught(
    tmp_path: Path, clean_mapping: Any
) -> None:
    mapping = clean_mapping["mapping-collection"]["mappings"][0]
    mapping["source-resource"]["href"] = "#99999999-8888-4777-8666-555555555555"
    assert "REFERENCE_UNRESOLVED" in _errors(write(tmp_path, "m.json", clean_mapping))


def test_a_duplicate_uuid_inside_a_mapping_is_caught(tmp_path: Path, clean_mapping: Any) -> None:
    collection = clean_mapping["mapping-collection"]
    _maps(clean_mapping)["uuid"] = collection["uuid"]
    assert "UUID_NOT_UNIQUE" in _errors(write(tmp_path, "m.json", clean_mapping))


def test_an_array_the_schema_requires_items_in_is_caught_inside_a_mapping(
    tmp_path: Path, clean_mapping: Any
) -> None:
    _maps(clean_mapping)["targets"] = []
    assert "ARRAY_TOO_SHORT" in _errors(write(tmp_path, "m.json", clean_mapping))


def test_one_mapping_written_as_an_object_is_read_like_a_list_of_one(
    tmp_path: Path, clean_mapping: Any
) -> None:
    """Both spellings the schema offers at ``mappings``, and both are checked.

    NIST writes ``mappings`` as an ``anyOf`` of one mapping or an array of
    mappings, the only place in the vendored schema that shape occurs. A
    document may use either, so a corruption must be caught in either, and a
    clean document must stay clean in either.
    """
    collection = clean_mapping["mapping-collection"]
    collection["mappings"] = collection["mappings"][0]
    assert not _errors(write(tmp_path, "one.json", clean_mapping)), (
        "the singleton spelling of a clean mapping is still clean"
    )
    assert "SUBTREE_NOT_READ" not in _codes(write(tmp_path, "one.json", clean_mapping))

    del collection["mappings"]["maps"][0]["relationship"]
    assert "REQUIRED_PROPERTY_MISSING" in _errors(write(tmp_path, "broken.json", clean_mapping)), (
        "a corruption inside the singleton spelling must be caught too"
    )


def test_a_scalar_where_the_schema_offers_one_mapping_or_many_is_caught(
    tmp_path: Path, clean_mapping: Any
) -> None:
    """A value that is neither one mapping nor an array of them.

    Both alternatives name the same definition, and that definition declares
    ``"type": "object"``, so the value is reported against a type the schema
    states rather than against a description of the choice.
    """
    clean_mapping["mapping-collection"]["mappings"] = "a string"
    assert "TYPE_MISMATCH" in _errors(write(tmp_path, "m.json", clean_mapping))


def _component_definition(start: float, end: float) -> dict[str, Any]:
    """The smallest conforming document that reaches OSCAL's bounded integers.

    ``port-range/start`` and ``port-range/end`` are the only two places the
    published schema uses ``NonNegativeIntegerDatatype``.
    """
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
                            "port-ranges": [{"start": start, "end": end, "transport": "TCP"}],
                        }
                    ],
                }
            ],
        }
    }
