"""Same input, byte-identical output. Twice, in separate processes, anywhere.

The last of those is not a flourish. ``docs/findings/`` is committed evidence,
and evidence a reader cannot regenerate is a claim rather than a measurement, so
the survey harness gets the same treatment as the validator here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from oscal_validate import __version__, validate_file
from oscal_validate.findings import render_findings_json

from .conftest import fixture_path, load_fixture, write

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from survey import _validate  # noqa: E402

FIXTURES = ["clean_catalog.json", "clean_profile.json"]


def test_validating_twice_gives_identical_findings() -> None:
    for name in FIXTURES:
        assert validate_file(fixture_path(name)) == validate_file(fixture_path(name)), name


def test_json_rendering_is_byte_identical_across_runs() -> None:
    for name in FIXTURES:
        first = render_findings_json(validate_file(fixture_path(name)), __version__, "catalog")
        second = render_findings_json(validate_file(fixture_path(name)), __version__, "catalog")
        assert first.encode("utf-8") == second.encode("utf-8"), name


def test_cli_output_is_byte_identical_across_processes() -> None:
    # Two separate interpreter processes: catches any hidden ordering that
    # depends on hash randomization or import order.
    command = [
        sys.executable,
        "-m",
        "oscal_validate",
        str(fixture_path("clean_profile.json")),
        "--resolve",
        str(fixture_path("clean_catalog.json")),
        "--format",
        "json",
    ]
    runs = [subprocess.run(command, capture_output=True, check=False) for _ in range(2)]
    assert runs[0].stdout == runs[1].stdout
    assert runs[0].stdout, "expected findings output"
    json.loads(runs[0].stdout)  # and it is valid JSON


def test_the_report_carries_no_timestamp_or_duration() -> None:
    payload = json.loads(
        render_findings_json(
            validate_file(fixture_path("clean_catalog.json")), __version__, "catalog"
        )
    )
    rendered = json.dumps(payload)
    for word in ("timestamp", "generated_at", "duration", "elapsed"):
        assert word not in rendered


# -- the survey harness: the evidence must not depend on where it was run ----
#
# A finding in a supporting document is located by the path that document was
# read from, so ``Finding.sort_key`` -- which leads with the location -- orders
# a corpus by a fact about one laptop. The harness records one example location
# per code, taking the first in that order, and moving the cache directory
# therefore moved the recorded example in 7 of the 52 published records. Counts
# never varied; the bookkeeping field did, which was enough to stop the
# committed artifact reproducing from a clean checkout.
#
# ``.cache`` and ``cache`` are two ordinary spellings of a cache directory, and
# they straddle the primary document's own pointers: ``.`` sorts before ``/``
# and ``c`` after it, so every supporting finding sorts before every primary one
# under the first spelling and after them under the second. That is the whole
# mechanism, reduced to something a test can hold.


def _corpus(tmp_path: Path, cache: str) -> dict[str, Any]:
    """A profile importing a profile importing a catalog, cached under ``cache``.

    Two levels, because the ordering only matters when one finding code occurs
    in both the primary document and a supporting one. ``IMPORT_RESOLVED`` does
    here: once for the top profile's import, once for the middle profile's.
    """
    catalog = load_fixture("clean_catalog.json")
    middle = load_fixture("clean_profile.json")
    top = {
        "profile": {
            "uuid": "9c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
            "metadata": {
                "title": "Synthetic Top Profile",
                "last-modified": "2026-08-14T00:00:00Z",
                "version": "1.0.0",
                "oscal-version": "1.2.3",
            },
            "imports": [
                {"href": "clean_profile.json", "include-controls": [{"with-ids": ["ex-1"]}]}
            ],
        }
    }
    source_of: dict[str, str] = {}
    for directory, name, document in (
        ("aa", "clean_profile.json", middle),
        ("bb", "clean_catalog.json", catalog),
    ):
        held = tmp_path / cache / directory
        held.mkdir(parents=True, exist_ok=True)
        write(held, name, document)
        source_of[f"{cache}/{directory}/{name}"] = f"https://example.org/{directory}/{name}"
    return _validate(
        write(tmp_path, "top.json", top),
        [Path(p) for p in source_of],
        source_of,
    )


def test_the_survey_records_the_same_example_wherever_the_cache_lives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    first = _corpus(tmp_path, ".cache")
    second = _corpus(tmp_path, "cache")

    assert first["codes"].get("IMPORT_RESOLVED") == 2, (
        "the fixture must put one code in both the primary and a supporting document, "
        "or this test cannot see the ordering it exists to pin"
    )
    assert first["codes"] == second["codes"]
    assert first["example_location"] == second["example_location"]


def test_the_survey_never_records_a_local_path_as_an_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every example is a JSON Pointer or a URL. A cache path is neither."""
    monkeypatch.chdir(tmp_path)
    for location in _corpus(tmp_path, ".cache")["example_location"].values():
        assert location.startswith(("/", "https://")), location
        assert ".cache" not in location, location
