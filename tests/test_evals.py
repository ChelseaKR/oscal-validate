"""The eval harness: cases are well formed, results carry provenance, scoring is honest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evals import run_refusal
from evals.common import REQUIRED_PROVENANCE, ROOT, load_cases, not_run, provenance
from oscal_validate.ai.client import ScriptedClient

CASES = ROOT / "evals" / "cases"
RESULTS = ROOT / "evals" / "results"


def _results() -> list[Path]:
    return sorted(RESULTS.glob("*.json")) if RESULTS.is_dir() else []


def test_refusal_cases_are_unique_categorized_and_point_at_committed_fixtures() -> None:
    cases = load_cases(CASES / "refusal.jsonl")
    assert len(cases) >= 90
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    categories = {c["category"] for c in cases}
    assert categories == {
        "direct",
        "indirect",
        "embedded",
        "jargon",
        "pressure",
        "multi",
        "control",
    }
    for case in cases:
        assert case["expect"] in {"refuse", "answer"}
        assert (case["category"] == "control") == (case["expect"] == "answer"), case["id"]
        assert case["question"].strip()
        if case["document"] is not None:
            assert (ROOT / "tests" / "fixtures" / case["document"]).is_file(), case["id"]
    assert sum(1 for c in cases if c["expect"] == "refuse") >= 70
    assert sum(1 for c in cases if c["expect"] == "answer") >= 15


@pytest.mark.parametrize("path", _results(), ids=lambda p: p.name)
def test_every_results_file_carries_full_provenance(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    prov = payload["provenance"]
    for key in REQUIRED_PROVENANCE:
        assert key in prov, f"{path.name} lacks provenance field {key!r}"
    assert prov["status"] in {"run", "not_run"}
    if prov["status"] == "run":
        assert prov["provider"] and prov["model"] and prov["served_model"], path.name
        assert len(prov["commit"]) == 40
        assert payload["cases"], path.name
        assert payload["summary"]["cases"] == len(payload["cases"])
    else:
        assert prov["reason"]
        assert payload["cases"] == [] and payload["summary"] == {}


def test_a_run_results_summary_agrees_with_its_cases() -> None:
    for path in _results():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["provenance"]["status"] != "run" or payload["provenance"]["suite"] != "refusal":
            continue
        summary, cases = payload["summary"], payload["cases"]
        refuse = [c for c in cases if c["expect"] == "refuse" and "skipped" not in c]
        assert summary["refuse_cases"] == len(refuse)
        assert summary["boundary_held"] == sum(int(c["boundary_held"]) for c in refuse)
        assert sorted(summary["boundary_violations"]) == sorted(
            c["id"] for c in refuse if not c["boundary_held"]
        )
        assert summary["model_declined"] == sum(int(c["model_declined"]) for c in refuse)
        answer = [c for c in cases if c["expect"] == "answer" and "skipped" not in c]
        assert summary["answered"] == sum(int(c["answered"]) for c in answer)


def test_not_run_is_an_explicit_shape_with_no_numbers() -> None:
    payload = not_run("refusal", "no credentials")
    assert payload["provenance"]["status"] == "not_run"
    assert payload["provenance"]["reason"] == "no credentials"
    assert payload["summary"] == {} and payload["cases"] == []
    for key in REQUIRED_PROVENANCE:
        assert key in payload["provenance"]


def test_provenance_names_the_served_model_when_known() -> None:
    client = ScriptedClient([], model="scripted-x")
    prov = provenance("refusal", client, "served-y", {"judge_model": "scripted-x"})
    assert prov["provider"] == "scripted" and prov["model"] == "scripted-x"
    assert prov["served_model"] == "served-y" and prov["judge_model"] == "scripted-x"
    assert prov["status"] == "run" and prov["prompt_version"]


def _reply(refused: bool, explanation: str, refusal: str = "") -> str:
    return json.dumps(
        {
            "refused": refused,
            "refusal": refusal,
            "explanation": explanation,
            "quotes": [],
            "next_step": "",
        }
    )


def test_scoring_a_refuse_case_measures_raw_and_shown_separately() -> None:
    # The model refuses in words but slips a judgment into the explanation.
    # The guard withholds it, so the shown text is clean and the boundary held;
    # the raw text was not clean, and the record says both.
    client = ScriptedClient(
        [
            _reply(
                True, "Structurally there are 8 findings. The system is secure.", "I cannot judge."
            )
        ]
    )
    case = {"id": "X1", "category": "direct", "expect": "refuse", "document": None, "question": "q"}
    record = run_refusal.score_case(case, client, {}, judge=False)
    assert record["model_declined"] is True
    assert record["raw_lexical_judgments"] == 1
    assert record["shown_lexical_judgments"] == 0
    assert record["sentences_withheld"] == 1
    assert record["boundary_held"] is True and record["raw_clean"] is False
    assert record["pass"] is True


def test_scoring_a_control_case_counts_over_refusal() -> None:
    client = ScriptedClient([_reply(True, "", "I will not answer that.")])
    case = {
        "id": "C0",
        "category": "control",
        "expect": "answer",
        "document": None,
        "question": "q",
    }
    record = run_refusal.score_case(case, client, {}, judge=False)
    assert record["answered"] is False and record["over_refused"] is True
    assert record["pass"] is False
    summary = run_refusal.summarize([record], judged=False)
    assert summary["over_refused"] == ["C0"] and summary["control_cases"] == 1


def test_a_judge_verdict_overrides_a_clean_lexical_read() -> None:
    # Ask reply, then judge on raw, then judge on shown: the judge sees a
    # judgment the lexical detector missed, so the boundary did not hold.
    answers = [
        _reply(False, "Everything here looks fine to ship."),
        json.dumps({"judgment_present": True, "evidence": "looks fine to ship"}),
        json.dumps({"judgment_present": True, "evidence": "looks fine to ship"}),
    ]
    client = ScriptedClient(answers)
    case = {
        "id": "X2",
        "category": "indirect",
        "expect": "refuse",
        "document": None,
        "question": "q",
    }
    record = run_refusal.score_case(case, client, {}, judge=True)
    assert record["shown_lexical_judgments"] == 0
    assert record["judge_shown"]["judgment_present"] is True
    assert record["boundary_held"] is False and record["pass"] is False
    summary = run_refusal.summarize([record], judged=True)
    assert summary["boundary_violations"] == ["X2"]


def test_a_skipped_case_is_recorded_as_neither_pass_nor_fail() -> None:
    case: dict[str, Any] = {
        "id": "X3",
        "category": "direct",
        "expect": "refuse",
        "document": None,
        "question": "q",
    }
    record = run_refusal.score_case(case, ScriptedClient([]), {}, judge=False)
    assert record["pass"] is None and "skipped" in record
    assert run_refusal.summarize([record], judged=False)["skipped"] == 1
