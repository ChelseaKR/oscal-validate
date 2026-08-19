"""The effective data model: what was supplied, and what that licenses."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

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


# --------------------------------------------------------------------------
# A document supplied twice is not a document withheld.
#
# ``--resolve`` is repeatable and takes directories as well as files, so the
# same file arrives twice for reasons that are not mistakes. Every spelling
# below used to make the import match two "different" supplied documents, which
# the tool reported as no document at all: the run came back with fewer settled
# references than passing the file once, and told the caller to supply a
# document they had just supplied.
# --------------------------------------------------------------------------


def _two_directories(tmp_path: Path, *, same_content: bool) -> tuple[Path, Path, Path]:
    """A profile, and two directories each holding a ``clean_catalog.json``."""
    catalog = json.loads(fixture_path("clean_catalog.json").read_text(encoding="utf-8"))
    first, second = tmp_path / "a", tmp_path / "b"
    for directory in (first, second):
        directory.mkdir()
        (directory / "clean_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    if not same_content:
        catalog["catalog"]["metadata"]["title"] = "A different catalog"
        (second / "clean_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    profile = tmp_path / "clean_profile.json"
    profile.write_text(fixture_path("clean_profile.json").read_text(encoding="utf-8"), "utf-8")
    return profile, first, second


@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param(lambda p, a, b: [a / "clean_catalog.json"], id="the file once"),
        pytest.param(
            lambda p, a, b: [a / "clean_catalog.json", a / "clean_catalog.json"],
            id="the same file twice",
        ),
        pytest.param(lambda p, a, b: [a, a], id="the same directory twice"),
        pytest.param(
            lambda p, a, b: [a, a / "clean_catalog.json"], id="a directory and a file in it"
        ),
        pytest.param(lambda p, a, b: [a, Path(f"{a}/")], id="a directory with and without a slash"),
        pytest.param(
            lambda p, a, b: [a / ".." / "a", a], id="the same directory by two different paths"
        ),
    ],
)
def test_naming_one_document_more_than_once_resolves_it_once(
    tmp_path: Path, spelling: Callable[[Path, Path, Path], list[Path]]
) -> None:
    profile, first, second = _two_directories(tmp_path, same_content=True)
    corpus = build_corpus(profile, spelling(profile, first, second), load_schema())
    assert corpus.complete
    assert corpus.edges[0].resolved
    assert not corpus.edges[0].ambiguous
    assert len(corpus.supporting) == 1
    assert len(corpus.reachable) == 2


def test_two_distinct_documents_of_one_name_are_ambiguous_not_absent(tmp_path: Path) -> None:
    """The one case that really is undetermined, and the one message for it.

    Two different files answering to one name is not a missing file. The
    documents were supplied; what cannot be determined is which one the import
    means. Reporting it as absent produced advice -- supply it with --resolve --
    that the caller had already followed, and that makes the run worse if
    followed again.
    """
    profile, first, second = _two_directories(tmp_path, same_content=False)
    corpus = build_corpus(profile, [first, second], load_schema())
    edge = corpus.edges[0]
    assert not corpus.complete
    assert edge.ambiguous
    assert not edge.resolved
    assert set(edge.candidates) == {
        str(first / "clean_catalog.json"),
        str(second / "clean_catalog.json"),
    }
    assert corpus.ambiguous_imports == (edge,)
    assert corpus.absent_imports == ()


def test_nothing_supplied_is_absent_and_not_ambiguous() -> None:
    corpus = build_corpus(fixture_path("clean_profile.json"), [], load_schema())
    edge = corpus.edges[0]
    assert edge.candidates == ()
    assert not edge.ambiguous
    assert corpus.absent_imports == (edge,)
    assert corpus.ambiguous_imports == ()
