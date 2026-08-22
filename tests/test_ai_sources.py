"""The corpus: hash-pinned, loadable, and able to verify the quotes the tool already makes."""

from __future__ import annotations

import hashlib
import json
import re

from oscal_validate import rules, validate_file
from oscal_validate.ai import sources
from oscal_validate.ai.sources import (
    CORPUS_DIR,
    REFERENCE_FOR_MODEL,
    constraint_snippet,
    contains,
    load,
    locate,
    manifest,
    normalize,
    passages_for_finding,
    passages_for_question,
    reference_section,
    sections,
    source_ids,
)

from .conftest import fixture_path


def test_every_corpus_file_matches_its_manifest_row_and_vice_versa() -> None:
    rows = manifest()
    files = {p.stem for p in CORPUS_DIR.glob("*.txt")}
    assert files == set(rows), "a text file without a manifest row, or the reverse"
    for identifier, row in rows.items():
        text = (CORPUS_DIR / f"{identifier}.txt").read_bytes()
        assert hashlib.sha256(text).hexdigest() == row["text_sha256"], identifier
        assert len(text) == int(row["text_bytes"]), identifier
        assert row["url"].startswith("https://pages.nist.gov/"), identifier
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["retrieved"]), identifier
        assert re.fullmatch(r"[0-9a-f]{64}", row["raw_sha256"]), identifier


def test_the_manifest_states_its_extraction_version_and_licence() -> None:
    payload = json.loads((CORPUS_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    assert payload["extraction_version"]
    assert "public domain" in payload["license"]


def test_every_source_id_loads_and_unknown_ids_do_not() -> None:
    ids = source_ids()
    assert len(ids) >= 20 + 14
    for identifier in ids:
        source = load(identifier)
        assert source is not None, identifier
        assert source.text and source.url and source.retrieved
    assert load("no-such-page") is None
    assert load("vendor:../SOURCES.md") is None
    assert load("vendor:nope.xml") is None


def test_the_prose_rules_the_tool_already_quotes_verify_against_the_corpus() -> None:
    """``rules.py`` quotes NIST verbatim. The corpus must contain those words."""
    expectations = {
        rules.UUID_GLOBALLY_UNIQUE: "identifier-use",
        rules.EFFECTIVE_DATA_MODEL: "uri-use",
        rules.CROSS_INSTANCE_SCOPE: "identifier-use",
    }
    for rule, source in expectations.items():
        # The longest quoted span in the citation is the NIST sentence; the
        # shorter ones are the page and section titles around it.
        quote = max(re.findall(r'"([^"]+)"', rule.citation), key=len)
        assert len(quote) >= 40, rule.citation
        assert contains(source, quote), f"{source} lacks: {quote[:60]}"
        assert source in locate(quote)


def test_a_short_or_invented_quote_never_verifies() -> None:
    assert not contains("identifier-use", "OSCAL")
    assert not contains("identifier-use", "OSCAL identifiers are always implemented correctly.")
    assert locate("this sentence does not appear in any NIST page at all") == []


def test_normalization_straightens_quotes_and_collapses_whitespace() -> None:
    assert normalize("OSCAL’s  machine-oriented\n UUID") == "OSCAL's machine-oriented UUID"


def test_reference_pages_index_by_json_pointer_path() -> None:
    section = reference_section("catalog", "/catalog/metadata/last-modified")
    assert section is not None
    assert section.path == ("catalog", "metadata", "last-modified")
    assert "Last Modified Timestamp" in section.text or "last-modified" in section.text
    # Array indexes are dropped, and a leaf the page does not name falls back
    # to its nearest described ancestor.
    deep = reference_section("catalog", "/catalog/groups/16/controls/23/parts/2/prose")
    assert deep is not None
    assert deep.path[:3] == ("catalog", "groups", "controls")
    assert reference_section("mapping-collection", "/mapping-collection/uuid") is None


def test_every_model_has_a_reference_page_with_its_root_section() -> None:
    for model, page in REFERENCE_FOR_MODEL.items():
        roots = [s for s in sections(page) if s.path == (model,)]
        assert roots, f"{page} has no root section for {model}"


def test_a_constraint_snippet_is_the_verbatim_element_from_the_vendored_file() -> None:
    snippet = constraint_snippet("oscal-catalog-controls", "oscal_catalog_metaschema_RESOLVED.xml")
    assert snippet is not None
    assert snippet.startswith("<index ")
    assert 'id="oscal-catalog-controls"' in snippet
    assert contains("vendor:oscal_catalog_metaschema_RESOLVED.xml", snippet)
    assert constraint_snippet("no-such-constraint", "oscal_catalog_metaschema_RESOLVED.xml") is None


def test_passages_for_every_fixture_finding_come_from_loadable_sources() -> None:
    findings = validate_file(fixture_path("clean_profile.json"))
    assert findings
    for finding in findings:
        passages = passages_for_finding(finding, "profile")
        assert passages, finding.code
        for passage in passages:
            assert load(passage.source) is not None, passage.source
            assert contains(passage.source, passage.text[:200]) or len(passage.text) < 20
        total = sum(len(p.text) for p in passages)
        assert total <= 24000


def test_passages_for_a_question_find_the_named_constraint_and_the_kind() -> None:
    passages = passages_for_question(
        "What does the is-unique constraint oscal-catalog-controls require?", model="catalog"
    )
    labels = {(p.source, p.label) for p in passages}
    assert ("vendor:oscal_catalog_metaschema_RESOLVED.xml", "oscal-catalog-controls") in labels
    assert any(p.source == "metaschema-constraints" for p in passages)


def test_reference_sections_are_excluded_from_question_retrieval_without_a_model() -> None:
    passages = passages_for_question("what is a back-matter resource")
    assert all(not p.source.startswith("reference-") for p in passages)
    assert sources.source_ids()  # the module is importable as a whole
