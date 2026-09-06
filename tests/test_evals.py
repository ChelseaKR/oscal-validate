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
        # Internal consistency is what a *partial* run satisfies perfectly:
        # a run of a third of the suite agrees with itself. Coverage is the
        # separate question, and it is declared wherever the suite's whole
        # case set is enumerated. The four results files committed on
        # 2026-08-21 predate the field, so it is checked when present rather
        # than required -- editing a record of a run to satisfy a later test
        # is its own bad idea. Anything produced since carries it.
        if "cases_missing" in prov:
            assert prov["cases_missing"] == [], (
                f"{path.name} covers only part of its suite; missing "
                f"{len(prov['cases_missing'])}: {prov['cases_missing'][:5]}"
            )
        if "cases_expected" in prov:
            assert payload["summary"]["cases"] == prov["cases_expected"], path.name
    else:
        assert prov["reason"]
        assert payload["cases"] == [] and payload["summary"] == {}


def test_the_results_provenance_gate_has_something_to_check() -> None:
    """A parametrized gate over an empty file set passes by having nothing to do."""
    assert _results(), "no results files: the provenance gate above cannot fail"


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


def _refusal_shard(path: Path, commit: str, records: list[dict[str, Any]], **prov: Any) -> Path:
    """A boundary-suite shard with the provenance a real one carries."""
    base: dict[str, Any] = {
        "suite": "refusal",
        "status": "run",
        "date": "2026-09-06",
        "tool_version": "0.0.0",
        "commit": commit,
        "provider": "scripted",
        "model": "m",
        "served_model": "m",
        "prompt_version": "v",
        "judge_model": "",
        "cases_file": "refusal.jsonl",
    }
    base.update(prov)
    path.write_text(
        json.dumps({"provenance": base, "summary": {}, "cases": records}), encoding="utf-8"
    )
    return path


def _refuse_record(case_id: str, held: bool) -> dict[str, Any]:
    return {
        "id": case_id,
        "category": "direct",
        "expect": "refuse",
        "boundary_held": held,
        "raw_clean": held,
        "raw_lexical_judgments": 0 if held else 1,
        "sentences_withheld": 0,
        "model_declined": False,
    }


def test_boundary_shards_merge_across_commits_and_still_refuse_an_overlap(tmp_path: Path) -> None:
    """The boundary suite merges through the same code the other two suites do.

    It used to have its own copy, which compared ``commit`` across shards and
    refused when they differed -- the normal case, since a shard records HEAD
    when it finishes and commits land while shards run, so a long sharded run
    could not be merged at all if anything landed underneath it. The union of
    commits is kept instead, and the checks that should still refuse a merge
    do: an overlap in case ids, and any real disagreement in provenance.
    """
    a = _refusal_shard(tmp_path / "a.json", "a" * 40, [_refuse_record("X1", True)])
    b = _refusal_shard(tmp_path / "b.json", "b" * 40, [_refuse_record("X2", False)])
    out = tmp_path / "merged.json"

    payload = run_refusal.merge([a, b], out)
    assert payload["summary"]["cases"] == 2
    assert payload["summary"]["boundary_held"] == 1
    assert payload["summary"]["boundary_violations"] == ["X2"]
    assert payload["provenance"]["commits"] == ["a" * 40, "b" * 40]
    assert payload["provenance"]["merged_from"] == ["a.json", "b.json"]
    assert json.loads(out.read_text(encoding="utf-8"))["summary"] == payload["summary"]

    with pytest.raises(SystemExit, match="overlap"):
        run_refusal.merge([a, a], out)
    judged = _refusal_shard(tmp_path / "c.json", "c" * 40, [], judge_model="m")
    with pytest.raises(SystemExit, match="disagree"):
        run_refusal.merge([a, judged], out)


def test_a_partial_boundary_run_declares_the_cases_it_did_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--ids`` is a supported way to run part of the suite, so the file says so.

    The boundary suite's whole case set is committed in
    ``cases/refusal.jsonl``, so a run always knows what it did not reach.
    Before this, a run of three cases wrote the same shape as a run of a
    hundred: ``status: run``, full provenance, and a summary that agreed
    with the three cases present.
    """
    monkeypatch.setattr(run_refusal, "client_from_env", lambda *a, **k: ScriptedClient([]))
    suite = load_cases(CASES / "refusal.jsonl")
    ran = [case["id"] for case in suite[:3]]
    out = tmp_path / "partial.json"

    assert run_refusal.main(["--ids", *ran, "--out", str(out)]) == 0

    prov = json.loads(out.read_text(encoding="utf-8"))["provenance"]
    assert prov["cases_expected"] == len(suite)
    assert prov["cases_missing"] == sorted(c["id"] for c in suite if c["id"] not in set(ran))
    assert len(prov["cases_missing"]) == len(suite) - len(ran)


def test_a_whole_boundary_run_declares_an_empty_missing_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coverage is stated, not inferred from silence."""
    monkeypatch.setattr(run_refusal, "client_from_env", lambda *a, **k: ScriptedClient([]))
    suite = load_cases(CASES / "refusal.jsonl")
    out = tmp_path / "whole.json"

    assert run_refusal.main(["--ids", *[c["id"] for c in suite], "--out", str(out)]) == 0

    prov = json.loads(out.read_text(encoding="utf-8"))["provenance"]
    assert prov["cases_missing"] == [] and prov["cases_expected"] == len(suite)


def test_merging_some_of_the_shards_says_which_cases_are_still_missing(tmp_path: Path) -> None:
    """Two of three shards is not a suite, and the merged file no longer says it is.

    Each shard's ``cases_missing`` is the whole set less its own ids, so the
    merged file's is their intersection: what no shard ran.
    """
    universe = ["X1", "X2", "X3", "X4"]

    def shard(name: str, ids: list[str]) -> Path:
        return _refusal_shard(
            tmp_path / name,
            name[0] * 40,
            [_refuse_record(i, True) for i in ids],
            cases_expected=len(universe),
            cases_missing=sorted(set(universe) - set(ids)),
        )

    a, b, c = shard("a.json", ["X1"]), shard("b.json", ["X2"]), shard("c.json", ["X3", "X4"])
    out = tmp_path / "merged.json"

    part = run_refusal.merge([a, b], out)
    assert part["summary"]["cases"] == 2
    assert part["provenance"]["cases_missing"] == ["X3", "X4"]

    whole = run_refusal.merge([a, b, c], out)
    assert whole["summary"]["cases"] == 4
    assert whole["provenance"]["cases_missing"] == []


def test_a_merge_refuses_a_mix_of_shards_that_declare_coverage_and_shards_that_do_not(
    tmp_path: Path,
) -> None:
    """Coverage cannot be averaged over shards that were not all asked for it.

    Merging a shard that declares what it did not run with one that says
    nothing would produce a merged file whose missing set is only as good as
    the shards that bothered -- which is the same silence in a new shape.
    """
    declared = _refusal_shard(
        tmp_path / "a.json",
        "a" * 40,
        [_refuse_record("X1", True)],
        cases_expected=2,
        cases_missing=["X2"],
    )
    # A shard from before the field existed carries neither half, and the
    # expected-count disagreement is what names it.
    older = _refusal_shard(tmp_path / "b.json", "b" * 40, [_refuse_record("X2", True)])
    with pytest.raises(SystemExit, match="cases_expected"):
        run_refusal.merge([declared, older], tmp_path / "merged.json")

    # One that agrees on the count but does not say what it missed is still
    # refused, rather than merged as though its silence meant nothing missing.
    half = _refusal_shard(
        tmp_path / "c.json", "c" * 40, [_refuse_record("X2", True)], cases_expected=2
    )
    with pytest.raises(SystemExit, match="coverage"):
        run_refusal.merge([declared, half], tmp_path / "merged.json")


def test_a_merge_keeps_every_shards_skipped_documents(tmp_path: Path) -> None:
    """The merged file used to publish the first shard's skip list as the run's.

    ``documents_skipped`` legitimately differs between shards -- a document
    absent from one machine's cache is skipped there and not elsewhere -- so
    it is not compared. It was also copied from the first shard alone, which
    made every other shard's skipped document disappear from the record.
    """
    a = _refusal_shard(
        tmp_path / "a.json",
        "a" * 40,
        [_refuse_record("X1", True)],
        documents_skipped=[],
    )
    b = _refusal_shard(
        tmp_path / "b.json",
        "b" * 40,
        [_refuse_record("X2", True)],
        documents_skipped=[{"id": "ifa_ssp", "reason": "not in the local cache"}],
    )
    merged = run_refusal.merge([a, b], tmp_path / "merged.json")
    assert merged["provenance"]["documents_skipped"] == [
        {"id": "ifa_ssp", "reason": "not in the local cache"}
    ]


def test_a_provenance_field_the_first_shard_lacks_is_still_compared(tmp_path: Path) -> None:
    """The agreement check read the first shard's field names and no others."""
    first = _refusal_shard(tmp_path / "a.json", "a" * 40, [_refuse_record("X1", True)])
    payload = json.loads(first.read_text(encoding="utf-8"))
    del payload["provenance"]["judge_model"]
    first.write_text(json.dumps(payload), encoding="utf-8")
    second = _refusal_shard(
        tmp_path / "b.json", "b" * 40, [_refuse_record("X2", True)], judge_model="m"
    )
    with pytest.raises(SystemExit, match="judge_model"):
        run_refusal.merge([first, second], tmp_path / "merged.json")
