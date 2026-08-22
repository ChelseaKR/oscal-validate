"""``repair --draft``: the validator, not the model, says what a patch did."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oscal_validate.ai import repair
from oscal_validate.ai.client import ScriptedClient
from oscal_validate.ai.run import prepare
from oscal_validate.cli import main
from oscal_validate.findings import Severity

from .conftest import fixture_path

CASSETTE = Path(__file__).resolve().parent / "cassettes" / "repair-broken-catalog.json"


def _reply(patch: list[dict[str, object]], **fields: object) -> str:
    base: dict[str, object] = {
        "refused": False,
        "refusal": "",
        "patch": patch,
        "rationale": "Give the second control its own id.",
        "quotes": [],
        "placeholders": [],
    }
    base.update(fields)
    return json.dumps(base)


def test_a_patch_that_resolves_the_finding_is_reported_by_revalidation() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    target = next(f for f in run.findings if f.code == "CONSTRAINT_NOT_UNIQUE")
    client = ScriptedClient(
        [_reply([{"op": "replace", "path": "/catalog/groups/0/controls/1/id", "value": "ex-2"}])]
    )
    result = repair.repair_one(run, target, client)
    assert result.skipped == ""
    assert result.outcome is not None
    assert result.outcome.resolved is True
    assert [f.code for f in result.outcome.also_resolved] == ["CONSTRAINT_NOT_UNIQUE"]
    assert result.outcome.introduced == []
    assert result.outcome.unchanged == 6
    assert result.outcome.before["ERROR"] == 3 and result.outcome.after["ERROR"] == 1
    assert '-            "id": "ex-1",' in result.outcome.diff
    assert '+            "id": "ex-2",' in result.outcome.diff
    # The original document in memory and on disk is untouched.
    assert run.payload["catalog"]["groups"][0]["controls"][1]["id"] == "ex-1"
    assert (
        json.loads(fixture_path("broken_catalog.json").read_text())["catalog"]["groups"][0][
            "controls"
        ][1]["id"]
        == "ex-1"
    )
    text = repair.render_text(result)
    assert "resolves F6; 6 finding(s) untouched; 1 other(s) also resolved" in text
    assert "proposed patch (RFC 6902, not applied)" in text


def test_a_patch_that_introduces_a_finding_says_so_and_does_not_claim_success() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    target = next(f for f in run.findings if f.code == "REQUIRED_PROPERTY_MISSING")
    client = ScriptedClient(
        [
            _reply(
                [
                    {"op": "add", "path": "/catalog/metadata/last-modified", "value": "2024-01-01"},
                    {"op": "add", "path": "/catalog/metadata/invented", "value": "x"},
                ]
            )
        ]
    )
    result = repair.repair_one(run, target, client)
    assert result.outcome is not None
    assert result.outcome.resolved is True  # the property is present now...
    codes = sorted(f.code for f in result.outcome.introduced)
    assert codes == ["DATATYPE_MISMATCH", "PROPERTY_UNDECLARED"]  # ...but the value and the extra
    assert "2 introduced" in repair.render_text(result)
    assert result.to_dict()["outcome"]["introduced"][0]["severity"] == "ERROR"


def test_a_patch_with_implementation_narrative_is_refused_whole() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    target = run.findings[-1]
    client = ScriptedClient(
        [
            _reply(
                [
                    {
                        "op": "add",
                        "path": "/catalog/metadata/remarks",
                        "value": "This control is fully implemented by the account process.",
                    }
                ]
            )
        ]
    )
    result = repair.repair_one(run, target, client)
    assert "boundary guard withholds" in result.skipped
    assert result.patch == [] and result.outcome is None
    assert "no draft:" in repair.render_text(result)


def test_unusable_patches_are_reported_not_shown() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    target = run.findings[-1]
    cases = {
        "no patch": _reply([]),
        "not usable": _reply([{"op": "move", "from": "/a", "path": "/b"}]),
        "cannot be applied": _reply([{"op": "replace", "path": "/catalog/nope", "value": 1}]),
        "not a list": json.dumps({"patch": "oops", "rationale": "", "quotes": []}),
        "unusable": "not json",
    }
    for expected, reply in cases.items():
        result = repair.repair_one(run, target, ScriptedClient([reply]))
        assert expected in result.skipped, (expected, result.skipped)
        assert result.outcome is None
    assert "model call failed" in repair.repair_one(run, target, ScriptedClient([])).skipped


def test_placeholders_are_taken_from_the_reply_and_detected_in_values() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    target = next(f for f in run.findings if f.code == "REQUIRED_PROPERTY_MISSING")
    reply = _reply(
        [
            {
                "op": "add",
                "path": "/catalog/metadata/last-modified",
                "value": "2024-01-01T00:00:00Z",
            },
            {"op": "replace", "path": "/catalog/metadata/title", "value": "TODO: real title"},
        ],
        placeholders=[{"path": "/catalog/metadata/last-modified", "why": "the real date"}],
    )
    result = repair.repair_one(run, target, ScriptedClient([reply]))
    assert result.placeholders == [
        {"path": "/catalog/metadata/last-modified", "why": "the real date"},
        {"path": "/catalog/metadata/title", "why": "the value is marked as a placeholder"},
    ]
    assert "placeholder at /catalog/metadata/title" in repair.render_text(result)


def test_write_out_refuses_the_original_and_resolve_paths(tmp_path: Path) -> None:
    run = prepare(fixture_path("clean_profile.json"), [fixture_path("clean_catalog.json")])
    draft = repair.Repair(label="F1", finding=run.findings[0], patched={"profile": {}})
    assert "refused" in repair.write_out(draft, run, fixture_path("clean_profile.json"))
    assert "refused" in repair.write_out(draft, run, fixture_path("clean_catalog.json"))
    out = tmp_path / "patched.json"
    assert "patched copy written" in repair.write_out(draft, run, out)
    assert json.loads(out.read_text(encoding="utf-8")) == {"profile": {}}
    empty = repair.Repair(label="F1", finding=run.findings[0])
    assert "nothing written" in repair.write_out(empty, run, tmp_path / "none.json")


def test_the_cli_requires_draft_and_writes_only_elsewhere(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = str(fixture_path("broken_catalog.json"))
    assert main(["repair", doc]) == 2
    assert "--draft" in capsys.readouterr().err

    monkeypatch.setenv("OSCAL_VALIDATE_AI_CASSETTE", str(CASSETTE))
    monkeypatch.delenv("OSCAL_VALIDATE_AI_RECORD", raising=False)
    out = tmp_path / "patched.json"
    code = main(["repair", "--draft", doc, "--label", "F8", "--out", str(out)])
    text = capsys.readouterr().out
    assert code == 0
    assert "resolves F8" in text
    assert f"patched copy written to {out}" in text
    assert "last-modified" in json.loads(out.read_text(encoding="utf-8"))["catalog"]["metadata"]

    code = main(["repair", "--draft", doc, "--severity", "ERROR", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["command"] == "repair"
    assert payload["provenance"]["model"] == "claude-sonnet-4-6"
    assert [d["label"] for d in payload["drafts"]] == ["F6", "F7", "F8"]
    for draft in payload["drafts"]:
        assert draft["outcome"]["resolved"] is True, draft["label"]
        assert draft["outcome"]["introduced"] == [], draft["label"]
        assert draft["withheld_sentences"] == 0


def test_refusing_to_overwrite_the_original_via_the_cli(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OSCAL_VALIDATE_AI_CASSETTE", str(CASSETTE))
    doc = str(fixture_path("broken_catalog.json"))
    assert main(["repair", "--draft", doc, "--label", "F8", "--out", doc]) == 0
    assert "refused to write" in capsys.readouterr().out
    assert any(
        f.severity is Severity.ERROR for f in prepare(fixture_path("broken_catalog.json")).findings
    )
