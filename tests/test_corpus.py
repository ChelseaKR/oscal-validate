"""The effective data model: what was supplied, and what that licenses."""

from __future__ import annotations

import json
from pathlib import Path

from oscal_validate.corpus import (
    IMPORT_SCALAR_NAMES,
    IMPORT_SEGMENTS,
    build_corpus,
    collect_paths,
    file_name_of,
)
from oscal_validate.schema import load_schema

from .conftest import fixture_path


def test_import_segments_exist_in_the_vendored_schema() -> None:
    # Every name this tool treats as an import must be a real property of a
    # real OSCAL model root, or the completeness claim is built on a typo.
    schema = load_schema()
    declared: set[str] = set()
    for root in schema.models.values():
        node = schema.resolve(root).node
        declared.update(node.get("properties", {}))
    assert declared >= IMPORT_SEGMENTS, IMPORT_SEGMENTS - declared


def test_the_source_reference_exists_in_the_vendored_schema() -> None:
    schema = load_schema()
    definition = schema.definitions[
        "oscal-complete-oscal-component-definition:control-implementation"
    ]
    assert set(definition["properties"]) >= IMPORT_SCALAR_NAMES


def test_a_document_that_imports_nothing_has_a_complete_effective_model() -> None:
    corpus = build_corpus(fixture_path("clean_catalog.json"), [], load_schema())
    assert corpus.edges == ()
    assert corpus.complete


def test_an_unsupplied_import_makes_the_effective_model_incomplete() -> None:
    corpus = build_corpus(fixture_path("clean_profile.json"), [], load_schema())
    assert len(corpus.edges) == 1
    assert not corpus.complete
    assert corpus.unresolved_imports[0].href == "clean_catalog.json"


def test_supplying_the_import_completes_it() -> None:
    corpus = build_corpus(
        fixture_path("clean_profile.json"), [fixture_path("clean_catalog.json")], load_schema()
    )
    assert corpus.complete
    assert len(corpus.reachable) == 2


def test_an_import_matches_a_different_serialization_by_stem(tmp_path: Path) -> None:
    profile = json.loads(fixture_path("clean_profile.json").read_text(encoding="utf-8"))
    profile["profile"]["imports"][0]["href"] = "../../catalog/xml/clean_catalog.xml"
    path = tmp_path / "p.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    corpus = build_corpus(path, [fixture_path("clean_catalog.json")], load_schema())
    assert corpus.complete


def test_file_name_of_reads_a_path_a_fragment_or_nothing() -> None:
    assert file_name_of("../../catalog/xml/basic-catalog.xml", {}) == "basic-catalog.xml"
    assert file_name_of("https://example.org/a/b/cat.json?x=1", {}) == "cat.json"
    assert file_name_of("#abc", {"abc": ["https://example.org/x/cat.json"]}) == "cat.json"
    assert file_name_of("#abc", {}) is None


def test_collect_paths_expands_a_directory() -> None:
    found = collect_paths([fixture_path("clean_catalog.json").parent])
    assert fixture_path("clean_catalog.json") in found
    assert all(path.suffix == ".json" for path in found)
