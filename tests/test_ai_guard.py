"""The boundary guard: judgments are withheld, boundary statements are kept."""

from __future__ import annotations

import pytest

from oscal_validate.ai.guard import WITHHELD, is_judgment, screen, screen_values

JUDGMENTS = [
    "This control is implemented.",
    "AC-2 is fully implemented by the described account management process.",
    "The system appears secure.",
    "This SSP is FedRAMP-ready.",
    "The package would be authorized as submitted.",
    "Overall, this system is compliant with NIST SP 800-53.",
    "The implementation satisfies AC-2.",
    "This meets the requirements of the moderate baseline.",
    "The residual risk is low.",
    "I recommend granting the ATO.",
    "The system is ready for authorization.",
    "This package is ready to submit to FedRAMP.",
    "The described safeguards are adequate.",
    "The control is in place and operating effectively.",
    "The SSP would pass a 3PAO assessment.",
    "The organization complies with HIPAA.",
    "This poses no security risk.",
    "The controls have been addressed.",
]

BOUNDARY_STATEMENTS = [
    "This tool cannot tell you whether a control is implemented.",
    "Whether the system is secure is a question for a qualified assessor.",
    "Structural conformance is not evidence that a control is implemented.",
    "I can't say whether this package would be authorized; that is an authorizing official's call.",
    "Nothing in a document's structure shows whether AC-2 is satisfied.",
    "You are asking whether the system is compliant, and that is outside what this tool does.",
    "The finding says the reference is dangling; it says nothing about whether the control is met.",
]

NEUTRAL = [
    "The schema declares last-modified in the required list of metadata.",
    "Two controls share the id ac-2, and the constraint requires it to be unique.",
    "Supply the imported catalog with --resolve to settle this.",
    "The link's href names #ac-2_smt.a.5, which no control statement declares.",
    "Add the missing property and re-run the validator.",
]


@pytest.mark.parametrize("sentence", JUDGMENTS)
def test_a_judgment_is_withheld(sentence: str) -> None:
    assert is_judgment(sentence), sentence
    result = screen(sentence)
    assert result.text == WITHHELD
    assert result.withheld == (sentence,)


@pytest.mark.parametrize("sentence", BOUNDARY_STATEMENTS + NEUTRAL)
def test_a_boundary_statement_or_neutral_sentence_is_kept(sentence: str) -> None:
    assert not is_judgment(sentence), sentence
    result = screen(sentence)
    assert result.text == sentence
    assert result.withheld == ()


def test_only_the_offending_sentence_moves_and_structure_is_kept() -> None:
    text = (
        "The finding is a dangling fragment. The control is implemented. "
        "Fix the href first.\n\nSecond paragraph stays."
    )
    result = screen(text)
    assert result.text == (
        f"The finding is a dangling fragment. {WITHHELD} Fix the href first.\n\n"
        "Second paragraph stays."
    )
    assert result.withheld_count == 1


def test_patch_values_are_screened_too() -> None:
    result = screen_values(["2026-08-14T00:00:00Z", "This control is implemented."])
    assert result.withheld_count == 1
    assert result.text.startswith("2026-08-14T00:00:00Z\n")


def test_an_empty_text_screens_to_itself() -> None:
    assert screen("").text == ""
    assert screen("\n\n").text == "\n\n"
