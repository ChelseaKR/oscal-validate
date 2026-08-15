"""Same input, byte-identical output. Twice, and in separate processes."""

from __future__ import annotations

import json
import subprocess
import sys

from oscal_validate import __version__, validate_file
from oscal_validate.findings import render_findings_json

from .conftest import fixture_path

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
