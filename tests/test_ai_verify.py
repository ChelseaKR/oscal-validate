"""The verifier: quotes checked against the corpus, prose screened, replies parsed strictly."""

from __future__ import annotations

import json

import pytest

from oscal_validate.ai.guard import WITHHELD
from oscal_validate.ai.verify import (
    INLINE_WITHHELD,
    ReplyError,
    parse_reply,
    render_quotes,
    render_withheld,
    verify,
)

#: A sentence that is really on the identifier-use page.
REAL = (
    "OSCAL's machine-oriented UUID identifiers are always globally-unique. Human-oriented "
    "identifiers must be defined and managed organizationally"
)


def test_parse_reply_accepts_bare_and_fenced_json_and_rejects_the_rest() -> None:
    assert parse_reply('{"a": 1}') == {"a": 1}
    assert parse_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_reply('Sure:\n{"a": 1}\nthanks') == {"a": 1}
    with pytest.raises(ReplyError, match="no JSON object"):
        parse_reply("no json here")
    with pytest.raises(ReplyError, match="not valid JSON"):
        parse_reply('{"a": }')


def test_a_verified_quote_is_kept_with_its_url_and_date() -> None:
    verified = verify(
        {
            "explanation": "UUIDs are global [Q1].",
            "quotes": [{"id": "Q1", "source": "identifier-use", "text": REAL}],
        },
        "explanation",
    )
    assert verified.clean
    assert verified.prose == "UUIDs are global [Q1]."
    assert [q.identifier for q in verified.quotes] == ["Q1"]
    assert verified.quotes[0].url.startswith("https://pages.nist.gov/")
    assert "retrieved" in render_quotes(verified.quotes)
    assert render_withheld(verified) == ""


def test_an_invented_quote_is_withheld_and_its_marker_struck() -> None:
    verified = verify(
        {
            "explanation": "NIST says so [Q1] and also [Q2] and [Q9].",
            "quotes": [
                {
                    "id": "Q1",
                    "source": "identifier-use",
                    "text": "NIST requires every UUID to be v7.",
                },
                {"id": "Q2", "source": "no-such-source", "text": REAL},
            ],
        },
        "explanation",
    )
    assert verified.prose == (
        "NIST says so [quote Q1 withheld] and also [quote Q2 withheld] and [quote Q9 withheld]."
    )
    reasons = {w.identifier: w.reason for w in verified.withheld_quotes}
    assert reasons["Q1"] == "not found verbatim in that source"
    assert reasons["Q2"] == "names a source that does not exist"
    assert reasons["Q9"] == "cited but never supplied"
    assert not verified.quotes
    assert "quote Q1 withheld from identifier-use" in render_withheld(verified)


def test_a_short_quote_is_withheld_as_unverifiable() -> None:
    verified = verify(
        {"explanation": "x [Q1]", "quotes": [{"id": "Q1", "source": "uri-use", "text": "OSCAL"}]},
        "explanation",
    )
    assert verified.withheld_quotes[0].reason == "too short to verify"


def test_an_inline_quotation_is_held_to_the_same_standard() -> None:
    invented = (
        "The validator shall consider every control implemented once its id is unique "
        "across the catalog."
    )
    literal = '"id": "ex-1" and the second control carries "id": "ex-1" as well'
    verified = verify(
        {
            "explanation": f'NIST writes "{REAL}" and also "{invented}" Here {literal}.',
            "quotes": [],
        },
        "explanation",
    )
    assert f'"{REAL}"' in verified.prose
    assert INLINE_WITHHELD in verified.prose
    assert invented not in verified.prose
    # JSON literals written into the prose are not quotations and are left alone.
    assert literal in verified.prose
    assert any("inline quotation" in w.reason for w in verified.withheld_quotes)


def test_a_judgment_in_the_prose_or_the_refusal_is_withheld_by_the_guard() -> None:
    verified = verify(
        {
            "refused": True,
            "refusal": "I cannot judge that. The system is secure though.",
            "explanation": "The id is duplicated. This control is fully implemented.",
            "quotes": [],
        },
        "explanation",
    )
    assert verified.refused
    assert verified.prose == f"The id is duplicated. {WITHHELD}"
    assert verified.refusal == f"I cannot judge that. {WITHHELD}"
    assert len(verified.withheld_sentences) == 2
    assert "2 sentence(s) withheld by the boundary guard" in render_withheld(verified)


def test_extra_fields_survive_and_missing_fields_default() -> None:
    verified = verify({"next_step": "add it", "patch": [1]}, "explanation")
    assert verified.prose == ""
    assert verified.extra == {"next_step": "add it", "patch": [1]}
    assert not verified.refused
    assert json.dumps(verified.extra)
