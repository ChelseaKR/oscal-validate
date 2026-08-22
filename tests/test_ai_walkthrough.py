"""``walkthrough``: nothing invented, nothing suppressed, order the tool's."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oscal_validate.ai import walkthrough
from oscal_validate.ai.client import ScriptedClient
from oscal_validate.ai.guard import WITHHELD
from oscal_validate.ai.run import prepare
from oscal_validate.cli import main

from .conftest import fixture_path

CASSETTE = Path(__file__).resolve().parent / "cassettes" / "walkthrough-nist-ssp.json"


def test_every_finding_lands_in_exactly_one_group_in_fix_order() -> None:
    run = prepare(fixture_path("nist_ssp_example.json"))
    groups = walkthrough.group(run)
    labels = [run.label(f) for g in groups for f in g.findings]
    assert sorted(labels, key=lambda x: int(x[1:])) == [run.label(f) for f in run.findings]
    assert len(labels) == len(set(labels)) == len(run.findings)
    assert [g.label for g in groups] == [f"G{i}" for i in range(1, len(groups) + 1)]
    codes = [g.code for g in groups]
    assert codes.index("IMPORT_NOT_SUPPLIED") < codes.index("REFERENCE_UNVERIFIABLE")
    assert codes.index("OSCAL_VERSION_DIFFERS") < codes.index("REFERENCE_UNVERIFIABLE")
    assert groups[0].tier == "Supply what the document imports"
    assert groups[0].severity == "INFO"


def test_the_broken_catalog_orders_structure_before_identifiers() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    codes = [g.code for g in walkthrough.group(run)]
    assert codes.index("REQUIRED_PROPERTY_MISSING") < codes.index("CONSTRAINT_NOT_UNIQUE")
    assert codes.index("CONSTRAINT_NOT_UNIQUE") < codes.index("CONSTRAINT_NOT_EVALUATED")


def test_a_prompt_block_shows_examples_and_counts_the_rest() -> None:
    run = prepare(fixture_path("nist_ssp_example.json"))
    groups = walkthrough.group(run)
    big = next(g for g in groups if g.code == "REFERENCE_UNVERIFIABLE")
    block = big.prompt_block(run)
    assert block.count("\n    F") == walkthrough.EXAMPLES_PER_GROUP
    assert f"... and {len(big.findings) - 3} more in {big.label}" in block


def _reply(**fields: object) -> str:
    base: dict[str, object] = {
        "refused": False,
        "refusal": "",
        "overview": "Start with G1.",
        "steps": [{"title": "Supply the import", "labels": ["G1"], "text": "Then F22 settles."}],
        "closing": "The rest stays UNVERIFIABLE.",
    }
    base.update(fields)
    return json.dumps(base)


def test_invented_labels_are_struck_and_uncovered_groups_appended() -> None:
    run = prepare(fixture_path("nist_ssp_example.json"))
    reply = _reply(
        steps=[
            {"title": "Fix G1 and G9", "labels": ["G1", "G9", "F999"], "text": "See F22 and F777."},
        ]
    )
    result = walkthrough.walk(run, ScriptedClient([reply]))
    assert result.invented == ["F777", "F999", "G9"]
    assert result.steps[0]["labels"] == ["G1"]
    assert "[label struck" in result.steps[0]["text"]
    assert "[label struck" in result.steps[0]["title"]
    assert result.covered == 1
    assert [g.label for g in result.not_covered] == ["G2", "G3", "G4", "G5"]
    text = walkthrough.render_text(result, run)
    assert "1 of 5 group(s) covered" in text
    assert walkthrough.NOT_COVERED in text
    assert "G5: UNVERIFIABLE REFERENCE_UNVERIFIABLE x16" in text
    assert "struck: F777, F999, G9" in text
    # The index lists every finding whether or not the narrative did.
    for finding in run.findings:
        assert f"{run.label(finding)} at={finding.location}" in text
    assert "index:" not in walkthrough.render_text(result, run, index=False)


def test_a_finding_label_counts_as_covering_its_group() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    groups = walkthrough.group(run)
    labels = {g.label: g for g in groups}
    f8 = next(g.label for g in groups if g.code == "REQUIRED_PROPERTY_MISSING")
    reply = _reply(
        overview="Start with F8 then the duplicate ids.",
        steps=[{"title": "Add last-modified", "labels": [], "text": "F8 first."}],
        closing="",
    )
    result = walkthrough.walk(run, ScriptedClient([reply]))
    assert labels[f8] not in result.not_covered
    assert result.covered == 1


def test_judgments_in_the_narrative_are_withheld() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    reply = _reply(
        overview="Fix the id. The catalog is now compliant.",
        steps=[{"title": "Ids", "labels": ["G1"], "text": "This control is implemented."}],
        closing="Done.",
    )
    result = walkthrough.walk(run, ScriptedClient([reply]))
    assert result.withheld_sentences == 2
    assert result.overview == f"Fix the id. {WITHHELD}"
    assert result.steps[0]["text"] == WITHHELD


def test_failures_and_empty_reports_show_nothing_from_the_model() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    failed = walkthrough.walk(run, ScriptedClient([]))
    assert "model call failed" in failed.skipped
    assert "no walkthrough" in walkthrough.render_text(failed, run)
    assert failed.to_dict(run)["skipped"] == failed.skipped
    unusable = walkthrough.walk(run, ScriptedClient(["nope"]))
    assert "unusable" in unusable.skipped
    run.findings = []
    run.labels = {}
    assert "no findings" in walkthrough.walk(run, ScriptedClient([])).skipped


def test_the_cli_replays_a_recorded_live_walkthrough(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recorded from Amazon Bedrock (claude-sonnet-4-6) on 2026-08-21 over NIST's SSP example."""
    monkeypatch.setenv("OSCAL_VALIDATE_AI_CASSETTE", str(CASSETTE))
    monkeypatch.delenv("OSCAL_VALIDATE_AI_RECORD", raising=False)
    doc = str(fixture_path("nist_ssp_example.json"))
    assert main(["walkthrough", doc, "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    w = payload["walkthrough"]
    assert payload["provenance"]["model"] == "claude-sonnet-4-6"
    assert w["groups_covered"] == len(w["groups"]) == 5
    assert w["invented_labels"] == [] and w["not_covered"] == []
    assert w["withheld_sentences"] == 0
    assert sum(g["count"] for g in w["groups"]) == 23
    assert main(["walkthrough", doc, "--no-index"]) == 0
    text = capsys.readouterr().out
    assert "5 of 5 group(s) covered" in text and "index:" not in text
