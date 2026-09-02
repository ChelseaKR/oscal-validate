"""The prompt is built from facts, not from the report's prose.

A model prompt that embeds the report's human-facing sentences makes every
copy edit to a report sentence a change to a recorded model interaction. That
is not hypothetical here: a ``CONSTRAINT_NOT_EVALUATED`` message stated
something false about NIST's ``allow-other`` semantics, and correcting it was
deferred because the correction could not be made without invalidating
``tests/cassettes/walkthrough-nist-ssp.json``. Prose a human reads should
never be held hostage to a recording.

These tests hold the separation open. The first states it structurally: the
built prompt contains no finding's message. The second states it in the form
the defect actually took: rewrite every message in the run and the prompt is
byte-identical, so the cassette key does not move.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from oscal_validate.ai import prompts, walkthrough
from oscal_validate.ai.client import prompt_key
from oscal_validate.ai.run import Run, prepare

from .conftest import fixture_path

FIXTURES = ("nist_ssp_example.json", "broken_catalog.json")


def _prompt(run: Run) -> str:
    groups = walkthrough.group(run)
    blocks = "\n\n".join(g.prompt_block(run) for g in groups)
    return prompts.walkthrough_user(run.model, blocks, run.notes_for())


def _rewrite_messages(run: Run) -> Run:
    """The same run with every report message replaced by unrelated prose."""
    rewritten = [
        replace(finding, message=f"COPY EDIT {index}: this sentence was reworded later.")
        for index, finding in enumerate(run.findings)
    ]
    labels = {new: run.labels[old] for old, new in zip(run.findings, rewritten, strict=True)}
    run.findings = rewritten
    run.labels = labels
    return run


def test_no_finding_message_reaches_the_walkthrough_prompt() -> None:
    for name in FIXTURES:
        run = prepare(fixture_path(name))
        built = _prompt(run)
        assert run.findings, name
        for finding in run.findings:
            head = finding.message[:60]
            assert head, name
            assert head not in built, f"{name}: a report message reached the prompt"


def test_rewriting_every_report_message_leaves_the_prompt_byte_identical() -> None:
    for name in FIXTURES:
        before = _prompt(prepare(fixture_path(name)))
        after = _prompt(_rewrite_messages(prepare(fixture_path(name))))
        assert before == after, f"{name}: report prose still moves the prompt"
        assert prompt_key(prompts.SYSTEM, before) == prompt_key(prompts.SYSTEM, after)


def test_the_prompt_still_carries_the_facts_a_narrative_needs() -> None:
    """Decoupling is not the same as starving the prompt."""
    run = prepare(fixture_path("broken_catalog.json"))
    built = _prompt(run)
    groups = walkthrough.group(run)
    assert groups
    for group in groups:
        assert group.label in built
        assert group.code in built
        assert group.tier in built
        # Each group shows its first few findings by label, with the rest counted.
        for finding in group.findings[: walkthrough.EXAMPLES_PER_GROUP]:
            assert run.label(finding) in built
            assert finding.location in built
            assert finding.prop in built


def test_the_declaration_file_is_the_only_place_staleness_is_recorded() -> None:
    """No second, drifting copy of the pending list."""
    declaration = Path(__file__).resolve().parent / "cassettes" / "pending-rerecord.json"
    assert declaration.is_file()
