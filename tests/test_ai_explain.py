"""``explain``: the validator runs first, the model is asked last, and the output is checked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oscal_validate.ai import explain
from oscal_validate.ai.client import ScriptedClient
from oscal_validate.ai.run import prepare
from oscal_validate.cli import main
from oscal_validate.findings import Severity

from .conftest import fixture_path, write

REAL = "OSCAL's machine-oriented UUID identifiers are always globally-unique."


def _reply(**fields: object) -> str:
    base: dict[str, object] = {
        "refused": False,
        "refusal": "",
        "explanation": "Two controls share one id [Q1].",
        "quotes": [{"id": "Q1", "source": "identifier-use", "text": REAL}],
        "next_step": "Give the second control its own id.",
    }
    base.update(fields)
    return json.dumps(base)


def test_prepare_labels_findings_in_report_order_and_keeps_the_document() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    assert run.model == "catalog"
    expected = [f"F{i}" for i in range(1, len(run.findings) + 1)]
    assert [run.label(f) for f in run.findings] == expected
    assert run.by_label("F1") is run.findings[0]
    assert run.by_label("F999") is None
    assert run.payload["catalog"]["metadata"]["title"]
    assert run.excerpt("/catalog/metadata").startswith("at /catalog:")
    assert "truncated" in run.excerpt("/catalog/metadata", limit=40)
    assert run.excerpt("/catalog/nope/3").startswith("at /:")  # falls back to the root


def test_notes_name_policy_rules_unverifiable_findings_and_version_skew(tmp_path: Path) -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    policy = next(f for f in run.findings if f.rule.url.startswith("README.md"))
    notes = run.notes_for(policy)
    assert any("own policy" in n for n in notes)
    assert any("UNVERIFIABLE" in n for n in notes)
    assert run.declared_version is None

    payload = json.loads(fixture_path("clean_catalog.json").read_text(encoding="utf-8"))
    payload["catalog"]["metadata"]["oscal-version"] = "1.1.2"
    skewed = prepare(write(tmp_path, "skewed.json", payload))
    assert skewed.declared_version == "1.1.2"
    assert any("issue #8" in n for n in skewed.notes_for())


def test_explain_one_sends_the_finding_and_evidence_and_verifies_the_reply() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    finding = next(f for f in run.findings if f.code == "REQUIRED_PROPERTY_MISSING")
    client = ScriptedClient([_reply()])
    result = explain.explain_one(run, finding, client)
    system, user = client.prompts[0]
    assert "cannot tell anyone whether a control is implemented" in system
    assert '"code": "REQUIRED_PROPERTY_MISSING"' in user
    assert "source: reference-catalog" in user
    assert result.verified is not None and result.verified.clean
    assert result.to_dict()["quotes"][0]["source"] == "identifier-use"
    text = explain.render_text(result)
    assert text.startswith("== F")
    assert "1 quote(s) verified, 0 withheld, 0 sentence(s) withheld" in text
    assert "next step: Give the second control its own id." in text


def test_an_unusable_reply_or_a_failed_call_shows_nothing_from_the_model() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    finding = run.findings[-1]
    bad = explain.explain_one(run, finding, ScriptedClient(["not json at all"]))
    assert bad.verified is None and "unusable" in bad.skipped
    assert "not explained" in explain.render_text(bad)
    failed = explain.explain_one(run, finding, ScriptedClient([]))
    assert "model call failed" in failed.skipped
    assert failed.to_dict()["skipped"] == failed.skipped


def test_judgments_and_invented_quotes_are_withheld_before_display() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    finding = run.findings[-1]
    reply = _reply(
        explanation="Add the property [Q1]. After that the control is fully implemented.",
        quotes=[{"id": "Q1", "source": "identifier-use", "text": "NIST mandates a v9 UUID here."}],
    )
    result = explain.explain_one(run, finding, ScriptedClient([reply]))
    assert result.verified is not None
    assert "[quote Q1 withheld]" in result.verified.prose
    assert "[withheld:" in result.verified.prose
    rendered = explain.render_text(result)
    assert "0 quote(s) verified, 1 withheld, 1 sentence(s) withheld" in rendered
    assert "fully implemented" not in rendered


def test_the_cli_explains_selected_findings_and_reports_provenance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A cassette with no entries and no inner client: every model call fails
    # loudly and nothing is fetched. The command still runs the validator and
    # still prints its banner and provenance.
    cassette = tmp_path / "empty.json"
    cassette.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OSCAL_VALIDATE_AI_CASSETTE", str(cassette))
    monkeypatch.delenv("OSCAL_VALIDATE_AI_RECORD", raising=False)
    code = main(["explain", str(fixture_path("broken_catalog.json")), "--severity", "ERROR"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("AI-generated text follows (cassette:empty.json")
    assert "3 explained" in out
    assert out.count("not explained: the model call failed") == 3

    code = main(
        ["explain", str(fixture_path("broken_catalog.json")), "--label", "F1", "--format", "json"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["command"] == "explain"
    assert payload["provenance"]["provider"] == "cassette"
    assert payload["provenance"]["prompt_version"]
    assert [e["label"] for e in payload["explanations"]] == ["F1"]


def test_the_cli_selects_by_code_and_limit_and_says_when_nothing_matched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cassette = tmp_path / "empty.json"
    cassette.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OSCAL_VALIDATE_AI_CASSETTE", str(cassette))
    doc = str(fixture_path("broken_catalog.json"))
    assert main(["explain", doc, "--code", "NO_SUCH_CODE"]) == 0
    assert "nothing was sent to the model" in capsys.readouterr().out
    assert main(["explain", doc, "--severity", "UNVERIFIABLE", "--limit", "1"]) == 0
    assert "1 explained" in capsys.readouterr().out


def test_an_unreadable_document_is_refused_before_any_model_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "bad.json"
    broken.write_text("{not json", encoding="utf-8")
    assert main(["explain", str(broken)]) == 2
    err = capsys.readouterr().err
    assert "nothing honest to explain" in err


def test_a_bad_provider_setting_is_an_error_not_a_guess(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OSCAL_VALIDATE_AI_CASSETTE", raising=False)
    monkeypatch.setenv("OSCAL_VALIDATE_AI_PROVIDER", "bedrock")
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    assert main(["explain", str(fixture_path("broken_catalog.json"))]) == 2
    assert "AWS_REGION" in capsys.readouterr().err


def test_the_broken_fixture_has_exactly_the_three_errors_the_tests_rely_on() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    errors = sorted(f.code for f in run.findings if f.severity is Severity.ERROR)
    assert errors == ["CONSTRAINT_NOT_UNIQUE", "CONSTRAINT_NOT_UNIQUE", "REQUIRED_PROPERTY_MISSING"]


CASSETTE = Path(__file__).resolve().parent / "cassettes" / "explain-broken-catalog.json"


def test_a_recorded_live_reply_replays_offline_and_its_quotes_verify(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cassette was recorded from Amazon Bedrock (claude-sonnet-4-6) on 2026-08-21.

    Replaying it here is the test that a real model's reply, not a scripted
    one, survives the verifier: every quote it made is found verbatim in the
    corpus, and nothing in it tripped the boundary guard. A prompt change
    misses the cassette by design; re-record it with OSCAL_VALIDATE_AI_RECORD=1.
    """
    monkeypatch.setenv("OSCAL_VALIDATE_AI_CASSETTE", str(CASSETTE))
    monkeypatch.delenv("OSCAL_VALIDATE_AI_RECORD", raising=False)
    doc = str(fixture_path("broken_catalog.json"))
    assert main(["explain", doc, "--severity", "ERROR", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provenance"]["model"] == "claude-sonnet-4-6"
    assert len(payload["explanations"]) == 3
    for item in payload["explanations"]:
        assert "skipped" not in item, item
        assert not item["refused"]
        assert len(item["quotes"]) >= 1, item["label"]
        assert item["withheld_quotes"] == [], item["label"]
        assert item["withheld_sentences"] == 0, item["label"]
        assert all(q["url"].startswith("https://") for q in item["quotes"])


def test_every_ai_command_discloses_what_it_sends_before_any_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Owner decision 2026-08-21: a one-line notice, on stderr, before the first network call."""
    cassette = tmp_path / "empty.json"
    cassette.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OSCAL_VALIDATE_AI_CASSETTE", str(cassette))
    monkeypatch.delenv("OSCAL_VALIDATE_AI_RECORD", raising=False)
    doc = str(fixture_path("broken_catalog.json"))
    # The cassette is empty, so every one of these fails to reach a model. The
    # notice is the subject here and must appear either way. The exit codes are
    # stated per command rather than assumed equal: `walkthrough` reports itself
    # NOT EVALUATED and exits 2 when it could not be produced, so that a stale
    # cassette cannot read as a walkthrough that came back with nothing to say
    # (see tests/test_ai_walkthrough.py). The other three still exit 0 on an
    # unreachable model; that difference is deliberate here and noted in
    # docs/ROADMAP.md rather than changed in passing.
    for argv, expected in (
        (["explain", doc, "--label", "F8"], 0),
        (["repair", "--draft", doc, "--label", "F8"], 0),
        (["walkthrough", doc, "--no-index"], 2),
        (["ask", "what is a catalog?", "--document", doc], 0),
    ):
        assert main(argv) == expected, argv[0]
        err = capsys.readouterr().err
        assert "this command sends" in err, argv[0]
        assert "the default validate command never does" in err, argv[0]
