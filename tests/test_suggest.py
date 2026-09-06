"""Near-miss identifiers for unresolved references (issue #64).

The 2026-08-15 imports survey measured 178 real unresolved references, and the
largest class of them was one zero-pad away from resolving. The report named
the failure and stopped. ``--suggest`` looks the neighbours up in the index the
resolution check already built, and these tests hold the four properties that
make that offer honest rather than merely helpful:

* it names what differs, from the documents supplied and nothing else;
* it says nothing when nothing is close;
* it says nothing at all when the effective data model is incomplete, because
  the nearest entry in an index known to be short is not evidence; and
* it changes no byte of a run that did not ask for it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from oscal_validate import cli
from oscal_validate.findings import Finding
from oscal_validate.suggest import MAX_SUGGESTIONS, distance, near_misses
from oscal_validate.validator import validate_file

from .conftest import load_fixture, write

CATALOG = "clean_catalog.json"


def _profile(with_ids: list[str], *, href: str = CATALOG) -> Any:
    profile = load_fixture("clean_profile.json")
    profile["profile"]["imports"] = [{"href": href, "include-controls": [{"with-ids": with_ids}]}]
    return profile


def _run(tmp_path: Path, with_ids: list[str], *, resolve: bool, suggest: bool) -> list[Finding]:
    write(tmp_path, CATALOG, load_fixture(CATALOG))
    document = write(tmp_path, "profile.json", _profile(with_ids))
    return validate_file(document, [tmp_path / CATALOG] if resolve else [], suggest=suggest)


def _unresolved(findings: list[Finding], value: str) -> Finding:
    matches = [f for f in findings if f.code.startswith("REFERENCE_") and f.value == value]
    assert len(matches) == 1, f"expected exactly one reference finding for {value!r}: {matches}"
    return matches[0]


# --- what the offer is ------------------------------------------------------


def test_a_zero_padded_control_reference_is_offered_the_identifier_that_exists(
    tmp_path: Path,
) -> None:
    """The survey's largest class, end to end: ``ex-01`` against a catalog with ``ex-1``."""
    findings = _run(tmp_path, ["ex-01", "ex-2"], resolve=True, suggest=True)
    finding = _unresolved(findings, "ex-01")

    assert finding.code == "REFERENCE_UNRESOLVED"
    # `ex-2` is two edits away and is a genuine near miss, so it is offered
    # too -- but the identifier that differs only by zero-padding ranks first,
    # which is the whole point of the ranking key.
    assert [s.value for s in finding.suggestions] == ["ex-1", "ex-2"]
    assert finding.suggestions[0].difference == "zero-padding"
    assert finding.suggestions[1].difference == "2 character edits"
    assert "also declared: ex-1  (differs by zero-padding)" in finding.render_text()
    rendered = finding.to_dict()["suggestions"]
    assert isinstance(rendered, list)
    assert rendered[0] == {"value": "ex-1", "difference": "zero-padding"}


def test_the_finding_itself_is_untouched_by_the_offer(tmp_path: Path) -> None:
    """A suggestion is not a downgrade: the code, severity and message do not move."""
    without = _unresolved(_run(tmp_path, ["ex-01"], resolve=True, suggest=False), "ex-01")
    with_ = _unresolved(_run(tmp_path, ["ex-01"], resolve=True, suggest=True), "ex-01")

    assert without.suggestions == ()
    assert with_.suggestions != ()
    assert (without.code, without.severity, without.message, without.location) == (
        with_.code,
        with_.severity,
        with_.message,
        with_.location,
    )


def test_nothing_within_the_bound_produces_no_offer(tmp_path: Path) -> None:
    """A dangling reference with no near neighbour prints no suggestion line."""
    finding = _unresolved(
        _run(tmp_path, ["completely-different-control"], resolve=True, suggest=True),
        "completely-different-control",
    )
    assert finding.suggestions == ()
    assert "also declared" not in finding.render_text()
    assert "suggestions" not in finding.to_dict()


def test_an_unverifiable_reference_never_carries_an_offer(tmp_path: Path) -> None:
    """The index that would be searched is incomplete, so its nearest entry proves nothing.

    This is the whole point of the UNVERIFIABLE severity, applied to the
    suggestion as well as to the finding: a run that has just said it could not
    perform the lookup must not then publish the closest thing it found.

    The fixture supplies **one** of two imported catalogs, which is the only
    shape in which this rule is testable. Omit both and the partial index is
    empty, so the search returns nothing whether or not the refusal is there --
    the check passes while enforcing nothing, and a later edit that deleted the
    refusal would look green. Here ``ex-1`` and ``ex-2`` are in the index from
    the catalog that *was* supplied, so a run that offered them would be caught.
    """
    write(tmp_path, CATALOG, load_fixture(CATALOG))
    profile = _profile(["ex-01"])
    profile["profile"]["imports"].append(
        {"href": "absent_catalog.json", "include-controls": [{"with-ids": ["ex-2"]}]}
    )
    document = write(tmp_path, "profile.json", profile)

    findings = validate_file(document, [tmp_path / CATALOG], suggest=True)
    finding = _unresolved(findings, "ex-01")

    assert finding.code == "REFERENCE_UNVERIFIABLE"
    assert finding.suggestions == (), (
        "an incomplete effective data model published its partial index's nearest "
        "entry as though the lookup had been made"
    )
    assert "also declared" not in finding.render_text()

    # The witness: with everything supplied, this same reference does get an
    # offer. Without this, the assertion above could be satisfied by a search
    # that never had anything to find.
    complete = _unresolved(_run(tmp_path, ["ex-01"], resolve=True, suggest=True), "ex-01")
    assert [s.value for s in complete.suggestions] == ["ex-1", "ex-2"]


def test_a_bare_fragment_is_offered_a_replacement_it_can_be_pasted_as(tmp_path: Path) -> None:
    """A ``#``-prefixed href gets a ``#``-prefixed answer, not a bare identifier."""
    write(tmp_path, CATALOG, load_fixture(CATALOG))
    profile = _profile(["ex-1"])
    profile["profile"]["metadata"]["links"] = [{"href": "#ex-01", "rel": "related"}]
    document = write(tmp_path, "profile.json", profile)

    findings = validate_file(document, [tmp_path / CATALOG], suggest=True)
    finding = _unresolved(findings, "#ex-01")

    assert [s.value for s in finding.suggestions] == ["#ex-1", "#ex-2"]
    assert all(s.value.startswith("#") for s in finding.suggestions)


# --- what the offer is not --------------------------------------------------


def test_the_offer_never_crosses_reference_kinds(tmp_path: Path) -> None:
    """A group identifier is not a candidate for a *control* reference.

    The catalog declares the group ``ex``, which is two edits from ``ex-3`` and
    would therefore be offered by a search over every identifier in the model.
    A control reference must never see it: the check being annotated would not
    accept a group id either, so offering one sends the reader to make an edit
    that cannot resolve. This case is chosen because the wrong-pool bug is
    *reachable* here -- a weaker fixture lets the same mistake pass silently,
    which is how a gate comes to look green while enforcing nothing.
    """
    write(tmp_path, CATALOG, load_fixture(CATALOG))
    document = write(tmp_path, "profile.json", _profile(["ex-3"]))

    findings = validate_file(document, [tmp_path / CATALOG], suggest=True)
    control = _unresolved(findings, "ex-3")

    assert [s.value for s in control.suggestions] == ["ex-1", "ex-2"]
    assert "ex" not in [s.value for s in control.suggestions], (
        "a group identifier was offered for a control reference: the candidate pool is "
        "the whole model rather than the identifiers this reference kind may name"
    )


def test_a_parameter_reference_is_offered_parameters(tmp_path: Path) -> None:
    """The other half of the same rule, from the other side."""
    write(tmp_path, CATALOG, load_fixture(CATALOG))
    profile = _profile(["ex-1"])
    profile["profile"]["modify"] = {"set-parameters": [{"param-id": "ex-1_prm_2", "values": ["v"]}]}
    document = write(tmp_path, "profile.json", profile)

    findings = validate_file(document, [tmp_path / CATALOG], suggest=True)
    parameter = _unresolved(findings, "ex-1_prm_2")

    assert [s.value for s in parameter.suggestions] == ["ex-1_prm_1"]


def test_the_offer_is_bounded_in_number_and_ordered_deterministically() -> None:
    """Ranking is the documented key, not dictionary order, and it is capped."""
    declared = {"ex-01", "EX-1", "ex_1", "ex-3", "ex-4", "ex-5", "ex-6"}
    offered = near_misses("ex-1", declared)

    assert len(offered) == MAX_SUGGESTIONS
    # Normalised-equal first, lexically among themselves; edit-distance
    # candidates come after, however many of them there are.
    assert [s.value for s in offered] == ["EX-1", "ex-01", "ex_1"]
    assert near_misses("ex-1", declared) == near_misses("ex-1", sorted(declared, reverse=True))


def test_every_named_difference_is_the_one_a_reader_has_to_fix() -> None:
    assert near_misses("ac-2", {"ac-02"})[0].difference == "zero-padding"
    assert near_misses("AC-02", {"ac-02"})[0].difference == "case"
    assert near_misses("ac_2", {"ac-2"})[0].difference == "the separator"
    assert near_misses("#ex-1", {"ex-1"})[0].difference == "a leading '#'"
    assert near_misses("AC_2", {"ac-02"})[0].difference == "case and the separator and zero-padding"
    assert near_misses("ac-3", {"ac-4"})[0].difference == "1 character edit"
    assert near_misses("ac-34", {"ac-43"})[0].difference == "1 character edit"


@pytest.mark.parametrize(
    ("written", "declared", "expected"),
    [
        ("abc", "abc", 0),
        ("abc", "abd", 1),
        ("abc", "acb", 1),  # one transposition, not two substitutions
        ("abc", "adbc", 1),
        ("abc", "xyz", None),  # 3 substitutions is past the cap
        ("a", "abcd", None),  # the length gate short-circuits
    ],
)
def test_the_distance_is_optimal_string_alignment_and_is_capped(
    written: str, declared: str, expected: int | None
) -> None:
    assert distance(written, declared) == expected


# --- the default path's bytes -----------------------------------------------


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_a_run_that_did_not_ask_produces_the_bytes_it_always_did(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fmt: str
) -> None:
    """The flag is opt-in, and on a document with offers available it changes nothing.

    ``tests/golden/`` pins the default path byte for byte, so a field that
    appeared unasked-for would move every golden at once. This is the same
    property measured on the one document where the difference would show.
    """
    write(tmp_path, CATALOG, load_fixture(CATALOG))
    document = write(tmp_path, "profile.json", _profile(["ex-01"]))
    argv = [str(document), "--resolve", str(tmp_path / CATALOG), "--format", fmt]

    assert cli.main(argv) == 1
    plain = capsys.readouterr().out
    assert cli.main([*argv, "--suggest"]) == 1
    suggested = capsys.readouterr().out

    assert "ex-1" not in plain.replace("ex-1_", "").replace('"ex-01"', "")
    assert plain != suggested, "the flag did nothing on a document where an offer exists"
    if fmt == "json":
        assert all("suggestions" not in f for f in json.loads(plain)["findings"])
        assert any("suggestions" in f for f in json.loads(suggested)["findings"])
    else:
        assert "also declared" not in plain
        assert "also declared: ex-1  (differs by zero-padding)" in suggested
