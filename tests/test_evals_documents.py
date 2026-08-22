"""Real-document evals: the documents are pinned, the defects are caught, the sums add up."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from evals import run_grounding, run_repair
from evals.common import merge_results, write_results
from evals.documents import DOCUMENTS, INJECTORS, load_documents, materialized
from oscal_validate import validate_file
from oscal_validate.ai.run import prepare
from oscal_validate.findings import Severity

from .conftest import fixture_path, load_fixture, write


def test_the_document_manifest_pins_twelve_nist_documents_across_the_models() -> None:
    manifest = json.loads(DOCUMENTS.read_text(encoding="utf-8"))
    docs = manifest["documents"]
    assert len(docs) == 12
    assert {d["model"] for d in docs} == {
        "catalog",
        "profile",
        "system-security-plan",
        "component-definition",
        "assessment-plan",
        "assessment-results",
        "plan-of-action-and-milestones",
    }
    for d in docs:
        assert d["url"].startswith("https://raw.githubusercontent.com/usnistgov/oscal-content/")
        assert len(d["sha256"]) == 64
    assert len({d["id"] for d in docs}) == 12


def test_the_fixture_backed_document_always_loads_and_absent_ones_are_skipped() -> None:
    found, skipped = load_documents()
    ids = {d.identifier for d in found}
    assert "ssp_example" in ids
    assert ids.isdisjoint({s["id"] for s in skipped})
    assert len(found) + len(skipped) == 12


@pytest.mark.parametrize("name", sorted(INJECTORS))
def test_each_injector_produces_a_new_error_the_validator_catches(
    name: str, tmp_path: Path
) -> None:
    original = load_fixture("clean_catalog.json")
    before = copy.deepcopy(original)
    corrupted = INJECTORS[name](original)
    assert original == before, "the injector mutated its input"
    if corrupted is None:
        pytest.skip(f"{name}: the clean catalog has no place for this defect")
    baseline = {(f.code, f.location) for f in validate_file(fixture_path("clean_catalog.json"))}
    new_errors = [
        f
        for f in validate_file(write(tmp_path, "clean_catalog.json", corrupted))
        if f.severity is Severity.ERROR and (f.code, f.location) not in baseline
    ]
    assert new_errors, name


def test_materialized_writes_the_copy_under_the_documents_own_name() -> None:
    found, _ = load_documents()
    document = next(d for d in found if d.identifier == "ssp_example")
    with materialized(document, {"x": 1}) as path:
        assert path.name == "nist_ssp_example.json"
        assert json.loads(path.read_text(encoding="utf-8")) == {"x": 1}
    assert not path.exists()


def test_injectors_decline_documents_without_a_place_for_the_defect() -> None:
    assert INJECTORS["break_uuid"]({"catalog": {"metadata": {}}}) is None
    assert INJECTORS["remove_required"]({"catalog": {"metadata": {}}}) is None
    assert INJECTORS["drop_timezone"]({"catalog": {"metadata": {"last-modified": "x"}}}) is None
    assert INJECTORS["wrong_type"]({"catalog": {"metadata": {}}}) is None
    assert INJECTORS["dangle_fragment"]({"catalog": {"metadata": {}}}) is None
    assert INJECTORS["duplicate_uuid"]({"catalog": {"uuid": "a", "metadata": {}}}) is None


def test_pick_findings_rotates_across_severities() -> None:
    run = prepare(fixture_path("nist_ssp_example.json"))
    chosen = run_grounding.pick_findings(run, 4)
    assert [f.severity.value for f in chosen] == ["WARNING", "INFO", "UNVERIFIABLE", "UNVERIFIABLE"]
    assert run_grounding.pick_findings(run, 0) == []


def test_repair_summary_counts_by_injector() -> None:
    records: list[dict[str, Any]] = [
        {"document": "a", "injector": "x", "resolved": True, "clean": True, "no_draft": False},
        {
            "document": "a",
            "injector": "x",
            "resolved": True,
            "clean": False,
            "introduced": ["P"],
            "no_draft": False,
        },
        {"document": "b", "injector": "y", "resolved": False, "clean": False, "no_draft": True},
        {"document": "b", "injector": "y", "skipped": "no place"},
    ]
    summary = run_repair.summarize(records)
    assert summary["cases"] == 4 and summary["skipped"] == 1 and summary["targets"] == 3
    assert summary["resolved"] == 2 and summary["clean"] == 1
    assert summary["introduced_any"] == 1 and summary["no_draft"] == 1
    assert summary["by_injector"]["x"] == {
        "n": 2,
        "resolved": 2,
        "clean": 1,
        "introduced": 1,
        "no_draft": 0,
    }
    assert summary["documents"] == ["a", "b"]


def test_grounding_summary_separates_explanations_from_walkthroughs() -> None:
    grounding: list[dict[str, Any]] = [
        {
            "document": "a",
            "label": "F1",
            "quotes_verified": 2,
            "quotes_withheld": 1,
            "inline_struck": 0,
            "sentences_withheld": 0,
            "grounded": True,
            "refused": False,
        },
        {
            "document": "a",
            "label": "F2",
            "quotes_verified": 0,
            "quotes_withheld": 2,
            "inline_struck": 1,
            "sentences_withheld": 1,
            "grounded": False,
            "refused": False,
        },
        {"document": "b", "label": "F1", "skipped": "failed"},
    ]
    walks: list[dict[str, Any]] = [
        {
            "document": "a",
            "groups": 5,
            "groups_covered": 5,
            "not_covered": [],
            "invented_labels": [],
            "sentences_withheld": 0,
            "complete": True,
            "faithful": True,
        },
        {
            "document": "b",
            "groups": 4,
            "groups_covered": 3,
            "not_covered": ["G4"],
            "invented_labels": ["F9"],
            "sentences_withheld": 2,
            "complete": False,
            "faithful": False,
        },
    ]
    summary = run_grounding.summarize(grounding, walks)
    g, w = summary["grounding"], summary["walkthrough"]
    assert g == {
        "explanations": 2,
        "skipped": 1,
        "quotes_verified": 2,
        "quotes_withheld": 3,
        "inline_struck": 1,
        "sentences_withheld": 1,
        "grounded": 1,
        "ungrounded": ["a:F2"],
        "refused": 0,
    }
    assert w["documents"] == 2 and w["complete"] == 1 and w["faithful"] == 1
    assert w["groups_total"] == 9 and w["groups_covered"] == 8 and w["invented_labels"] == 1


def _shard(path: Path, suite: str, cases: list[dict[str, Any]], commit: str = "c" * 40) -> Path:
    write_results(
        path,
        {
            "provenance": {
                "suite": suite,
                "status": "run",
                "date": "2026-08-21",
                "tool_version": "0.2.0",
                "commit": commit,
                "provider": "bedrock",
                "model": "m",
                "served_model": "m",
                "prompt_version": "v",
            },
            "summary": {},
            "cases": cases,
        },
    )
    return path


def test_merging_shards_unions_cases_keeps_every_commit_and_refuses_overlap(tmp_path: Path) -> None:
    a = _shard(
        tmp_path / "a.json",
        "repair",
        [{"document": "a", "injector": "x", "resolved": True, "clean": True, "no_draft": False}],
        "a" * 40,
    )
    b = _shard(
        tmp_path / "b.json",
        "repair",
        [{"document": "b", "injector": "x", "resolved": False, "clean": False, "no_draft": True}],
        "b" * 40,
    )
    out = tmp_path / "merged.json"
    payload = merge_results([a, b], out, run_repair.summarize, lambda r: r["document"])
    assert payload["summary"]["targets"] == 2
    assert payload["provenance"]["commits"] == ["a" * 40, "b" * 40]
    assert payload["provenance"]["merged_from"] == ["a.json", "b.json"]
    assert json.loads(out.read_text(encoding="utf-8"))["summary"] == payload["summary"]
    with pytest.raises(SystemExit, match="overlap"):
        merge_results([a, a], out, run_repair.summarize, lambda r: r["document"])
    other = _shard(tmp_path / "c.json", "grounding", [])
    with pytest.raises(SystemExit, match="disagree"):
        merge_results([a, other], out, run_repair.summarize, lambda r: r["document"])
