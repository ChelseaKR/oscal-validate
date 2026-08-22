"""``ask``: a question answered from the corpus, with a document's findings as context."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oscal_validate.ai import ask
from oscal_validate.ai.client import ScriptedClient
from oscal_validate.ai.run import prepare
from oscal_validate.cli import main

from .conftest import fixture_path

REAL = (
    "The effective data model of a document includes all objects identified with the "
    "document and any directly or transitively imported documents."
)


def _reply(**fields: object) -> str:
    base: dict[str, object] = {
        "refused": False,
        "refusal": "",
        "explanation": "NIST defines it as [Q1].",
        "quotes": [{"id": "Q1", "source": "uri-use", "text": REAL}],
        "next_step": "",
    }
    base.update(fields)
    return json.dumps(base)


def test_a_question_without_a_document_gets_corpus_evidence_only() -> None:
    client = ScriptedClient([_reply()])
    answer = ask.ask_one("What is the effective data model?", client)
    _, user = client.prompts[0]
    assert "Evidence you may quote" in user
    assert "finding(s) from the validator" not in user
    assert answer.verified is not None and answer.verified.clean
    assert answer.to_dict()["quotes"][0]["source"] == "uri-use"
    assert "1 quote(s) verified" in ask.render_text(answer)


def test_a_question_with_a_document_sees_the_validators_findings_as_labels() -> None:
    run = prepare(fixture_path("broken_catalog.json"))
    client = ScriptedClient([_reply()])
    ask.ask_one("What is wrong with this catalog?", client, run)
    _, user = client.prompts[0]
    context = ask.findings_context(run)
    assert context in user
    assert "Document model: catalog; 8 finding(s)" in context
    assert "F8 ERROR REQUIRED_PROPERTY_MISSING" in context


def test_a_long_findings_list_is_cut_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    run = prepare(fixture_path("nist_ssp_example.json"))
    monkeypatch.setattr(ask, "FINDINGS_SHOWN", 5)
    context = ask.findings_context(run)
    assert "... and 18 more" in context
    assert "issue #8" in context


def test_a_refusal_is_rendered_and_judgments_in_it_are_still_screened() -> None:
    reply = _reply(
        refused=True,
        refusal="I cannot say whether AC-2 is implemented. The system is secure though.",
        explanation="Structurally, no finding names AC-2.",
        quotes=[],
    )
    answer = ask.ask_one("Is AC-2 implemented?", ScriptedClient([reply]))
    text = ask.render_text(answer)
    assert "refused: I cannot say whether AC-2 is implemented. [withheld:" in text
    assert "secure though" not in text
    assert "1 sentence(s) withheld" in text


def test_failures_show_nothing_from_the_model() -> None:
    bad = ask.ask_one("q", ScriptedClient(["<html>"]))
    assert "unusable" in bad.skipped and "not answered" in ask.render_text(bad)
    assert bad.to_dict() == {"question": "q", "skipped": bad.skipped}
    failed = ask.ask_one("q", ScriptedClient([]))
    assert "model call failed" in failed.skipped


def test_the_cli_asks_with_and_without_a_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cassette = tmp_path / "empty.json"
    cassette.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OSCAL_VALIDATE_AI_CASSETTE", str(cassette))
    monkeypatch.delenv("OSCAL_VALIDATE_AI_RECORD", raising=False)
    assert main(["ask", "What is a catalog?"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("AI-generated text follows")
    assert "not answered: the model call failed" in out

    doc = str(fixture_path("broken_catalog.json"))
    assert main(["ask", "What is wrong?", "--document", doc, "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "ask"
    assert payload["document"] == {"path": "broken_catalog.json", "model": "catalog"}
    assert payload["provenance"]["provider"] == "cassette"

    bad = tmp_path / "bad.json"
    bad.write_text("nope", encoding="utf-8")
    assert main(["ask", "What is wrong?", "--document", str(bad)]) == 2
