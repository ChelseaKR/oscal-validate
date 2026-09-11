"""``tools/revendor.py``: what a new OSCAL release would change, before it is paid for.

Five properties, each with an input that can fail it.

**An unchanged snapshot is empty, and its counts are the parser's.** The first
version of this harness keyed constraints by identifier, folded NIST's 340 into
324, and printed the fold as the release. The counts are now asserted against
``load_metaschema()`` directly, and every constraint must get a key of its own.

**Every kind of change is named**: a re-level, a re-target outside the parsed
grammar, and a change of bytes that no inventory row records. The last is the
one that matters most, because the inventory does not describe an
``allowed-values`` set, and a harness that decided "unchanged" from the
inventory alone would call such a release unchanged.

**Golden impact says what moved and why.** A change in which constraints are
evaluated moves every golden, by one finding: every report restates the
release-wide count of constraints this tool does not evaluate. The harness
names that finding rather than reporting twelve unexplained alarms, and a
change the goldens cannot see says so, with its denominator.

**Refusals**: a DTD, a missing file, a robots.txt disallow, and an inventory
that would have described the installed package instead of the copy.

**Writing moves only what it should, and a dry run moves nothing.**

Every fixture is the vendored snapshot copied and edited in exactly one place,
with the edit's anchor asserted to appear once and the file's hash asserted to
have moved. Golden runs are a subprocess per case per format, so the tests that
assert nothing about goldens call ``change_for`` directly, and two that assert
"no golden moved" over a change that cannot reach an evaluated finding limit
the run to the committed cases and say so.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from oscal_validate.metaschema import load_metaschema

from .golden.capture import CACHED, CASES
from .test_survey_fetch import ALLOW_ALL, Route, robots, serve

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import revendor  # noqa: E402
from fetch import Fetcher  # noqa: E402

VENDOR = ROOT / "src" / "oscal_validate" / "vendor"
OSCAL = VENDOR / "oscal"
CATALOG = "oscal_catalog_metaschema_RESOLVED.xml"

#: The declaring element of an evaluated catalog constraint, byte for byte as
#: NIST publishes it in 1.2.3. Anchored on its own id, so it is unique.
CONTROLS_INDEX = (
    '<index id="oscal-catalog-controls"\n'
    '                 name="catalog-controls"\n'
    '                 target="//control">'
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(tmp_path: Path) -> Path:
    directory = tmp_path / "candidate"
    shutil.copytree(OSCAL, directory)
    return directory


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{path.name}: the anchor appears {text.count(old)} times"
    before = _digest(path)
    path.write_text(text.replace(old, new), encoding="utf-8")
    assert _digest(path) != before, f"{path.name}: the edit did not land"


def _change(directory: Path) -> dict[str, Any]:
    candidate = revendor.from_directory(directory)
    with revendor.package_copy(candidate) as src:
        return revendor.change_for(candidate, src)


def _impact(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = revendor.from_directory(directory)
    with revendor.package_copy(candidate) as src:
        return revendor.change_for(candidate, src), revendor.golden_impact(src)


def _only(change: dict[str, Any], *populated: str) -> None:
    """Every constraint list except the named ones is empty."""
    for name in ("added", "removed", "relevelled", "retargeted", "now_evaluated", "now_skipped"):
        rows = change["constraints"][name]
        assert bool(rows) == (name in populated), (name, rows)


def _vendor_digests() -> dict[str, str]:
    return {path.name: _digest(path) for path in sorted(VENDOR.rglob("*")) if path.is_file()}


# -- an unchanged snapshot ---------------------------------------------------


def test_an_unchanged_snapshot_is_empty_and_its_counts_are_the_parser_s(tmp_path: Path) -> None:
    metaschema = load_metaschema()
    change = _change(_candidate(tmp_path))
    counts = change["constraints"]
    assert counts["published"] == {
        "from": len(metaschema.constraints),
        "to": len(metaschema.constraints),
    }
    assert counts["evaluated"] == {
        "from": len(metaschema.evaluated()),
        "to": len(metaschema.evaluated()),
    }
    assert change["files"]["changed"] == []
    assert revendor.is_empty(change)


def test_every_constraint_gets_a_key_of_its_own() -> None:
    """The collapse from 340 to 324, prevented rather than recounted."""
    constraints = revendor.inventory(ROOT / "src")["constraints"]
    assert len(constraints) == len(load_metaschema().constraints)
    assert len(revendor.keyed(constraints)) == len(constraints)


def test_the_inventory_refuses_to_describe_a_package_it_did_not_import(tmp_path: Path) -> None:
    """Pointed at a directory with no package in it, the subprocess still finds one.

    The editable install is importable from this interpreter, so an inventory
    of an empty directory would quietly be the installed package describing
    itself -- exactly the contamination a candidate copy exists to avoid.
    """
    (tmp_path / "src").mkdir()
    with pytest.raises(revendor.RevendorError) as refused:
        revendor.inventory(tmp_path / "src")
    assert "not the copy" in str(refused.value)


# -- every kind of change is named -------------------------------------------


def test_a_relevelled_constraint_is_named_and_no_golden_can_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#69's re-level, and the measurement that decides what "the golden it moves" can mean.

    Not one golden finding in this repository comes from an evaluated
    constraint, so a level change reaches no golden. The harness says that
    with its denominator rather than printing a bare zero. Limited to the
    committed cases: the claim is about evaluated findings, and none of the
    committed goldens carries one either.
    """
    monkeypatch.setattr(revendor, "CACHED", [])
    directory = _candidate(tmp_path)
    _edit(
        directory / CATALOG,
        '<index id="oscal-catalog-controls"',
        '<index id="oscal-catalog-controls" level="WARNING"',
    )
    change, impact = _impact(directory)
    _only(change, "relevelled")
    [row] = change["constraints"]["relevelled"]
    assert "oscal-catalog-controls" in row["constraint"]
    assert (row["from"], row["to"]) == ("ERROR", "WARNING")
    assert [f["file"] for f in change["files"]["changed"]] == [CATALOG]
    assert impact["moved"] == []
    assert impact["golden_findings"] > 0, "a zero denominator would make the next line vacuous"
    assert impact["golden_findings_from_evaluated_constraints"] == 0


def test_a_change_no_inventory_row_records_is_still_a_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The witness for "the bytes decide": an allowed-values set is not in the inventory."""
    monkeypatch.setattr(revendor, "CACHED", [])
    directory = _candidate(tmp_path)
    _edit(
        directory / CATALOG,
        '<enum value="resolution-tool"',
        '<enum value="resolution-tool-renamed"',
    )
    change, impact = _impact(directory)
    _only(change)
    assert not any(change["definitions"].values())
    assert [f["file"] for f in change["files"]["changed"]] == [CATALOG]
    assert not revendor.is_empty(change)
    text = revendor.render_text(change, impact, [])
    assert "the bytes differ in ways this inventory does not record" in text


def test_a_retarget_outside_the_grammar_moves_every_golden_by_the_release_wide_count_alone(
    tmp_path: Path,
) -> None:
    """Every golden moves, and in each the only finding that moved is that count.

    Written first as "exactly the goldens of a catalog move" -- the premise
    came from how constraints are *evaluated*, which is scoped to a document's
    model. All twelve moved. The report is built elsewhere: every report's
    ``CONSTRAINT_NOT_EVALUATED`` finding counts the release's unevaluated
    constraints with no model filter, so an SSP's golden moved by the same four
    lines as a catalog's. The assertion is still two-sided: a golden that moved
    for any other reason, or by any other finding, fails it.
    """
    directory = _candidate(tmp_path)
    _edit(
        directory / CATALOG,
        CONTROLS_INDEX,
        CONTROLS_INDEX.replace('target="//control"', "target=\"doc('elsewhere.xml')//control\""),
    )
    change, impact = _impact(directory)
    _only(change, "retargeted", "now_skipped")
    [skipped] = change["constraints"]["now_skipped"]
    [moved_target] = change["constraints"]["retargeted"]
    assert moved_target["constraint"] == skipped["constraint"]
    assert "oscal-catalog-controls" in skipped["constraint"]
    assert (moved_target["from"], moved_target["to"]) == (
        "//control",
        "doc('elsewhere.xml')//control",
    )
    assert "doc()" in skipped["because"]
    assert [row["constraint"] for row in change["outside_the_grammar"]] == [skipped["constraint"]]

    ran = [name for name, _, _ in CASES] + [
        name for name, _ in CACHED if name not in impact["cases_not_run"]
    ]
    assert ran and len(ran) == impact["cases_run"]
    assert sorted(row["golden"] for row in impact["moved"]) == sorted(ran)
    for row in impact["moved"]:
        assert row["codes"] == [revendor.NOT_EVALUATED], row
        assert row["findings"]["changed"] == 1, row
        assert sum(count for key, count in row["findings"].items() if key != "changed") == 0, row
    text = revendor.render_text(change, impact, [])
    assert all(f"  {name} (" in text for name in ran)
    assert "restates the release-wide count" in text


# -- refusals ----------------------------------------------------------------


def test_a_candidate_carrying_a_dtd_is_refused_before_anything_reads_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _candidate(tmp_path)
    module = directory / CATALOG
    module.write_bytes(b'<!DOCTYPE x [<!ENTITY a "a">]>\n' + module.read_bytes())
    with pytest.raises(revendor.RevendorError, match="DOCTYPE"):
        revendor.from_directory(directory)
    assert revendor.main(["--from-dir", str(directory)]) == 2
    assert "refused before anything reads it" in capsys.readouterr().err


def test_a_missing_file_is_refused_by_name(tmp_path: Path) -> None:
    directory = _candidate(tmp_path)
    (directory / CATALOG).unlink()
    with pytest.raises(revendor.RevendorError, match=CATALOG):
        revendor.from_directory(directory)


def _release_routes(version: str) -> dict[str, Route]:
    return {
        f"/releases/download/v{version}/{revendor.original_name(name)}": Route(
            body=(OSCAL / name).read_bytes(), content_type="application/octet-stream"
        )
        for name in revendor.NAMES
    }


def test_a_release_is_fetched_through_the_robots_first_fetcher(tmp_path: Path) -> None:
    routes = {"/robots.txt": ALLOW_ALL, **_release_routes("9.9.9")}
    with serve(routes) as site:
        candidate = revendor.by_fetch(
            "9.9.9",
            Fetcher(min_interval=0.0, timeout=5.0),
            tmp_path,
            release_url=f"{site.base}/releases/download/v{{version}}/{{name}}",
        )
        requested = [path for path, _ in site.requests]
    assert requested[0] == "/robots.txt", "robots.txt must be read before any file"
    assert {name: record.sha256 for name, record in candidate.files.items()} == {
        name: _digest(OSCAL / name) for name in revendor.NAMES
    }
    assert all(record.source.startswith(site.base) for record in candidate.files.values())
    assert all(record.fetched_at not in ("", "-") for record in candidate.files.values())


def test_a_robots_disallow_stops_the_fetch_and_names_the_file(tmp_path: Path) -> None:
    routes = {"/robots.txt": robots("User-agent: *\nDisallow: /\n"), **_release_routes("9.9.9")}
    with serve(routes) as site, pytest.raises(revendor.RevendorError, match="BlockedError"):
        revendor.by_fetch(
            "9.9.9",
            Fetcher(min_interval=0.0, timeout=5.0),
            tmp_path,
            release_url=f"{site.base}/releases/download/v{{version}}/{{name}}",
        )
    assert list(tmp_path.iterdir()) == [], "a refused fetch must write nothing"


# -- writing -----------------------------------------------------------------


def test_write_moves_exactly_the_changed_file_and_its_hash_row(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor"
    shutil.copytree(VENDOR, vendor)
    sources_before = (vendor / "SOURCES.md").read_text(encoding="utf-8").splitlines()
    directory = _candidate(tmp_path)
    _edit(
        directory / CATALOG,
        '<index id="oscal-catalog-controls"',
        '<index id="oscal-catalog-controls" level="WARNING"',
    )
    candidate = revendor.from_directory(directory)
    remaining = revendor.write(candidate, vendor=vendor)

    assert _digest(vendor / "oscal" / CATALOG) == _digest(directory / CATALOG)
    sources_after = (vendor / "SOURCES.md").read_text(encoding="utf-8").splitlines()
    moved = [(a, b) for a, b in zip(sources_before, sources_after, strict=True) if a != b]
    assert len(moved) == 1
    assert CATALOG in moved[0][1]
    assert _digest(directory / CATALOG) in moved[0][1]
    assert any("test_vendor_integrity.py" in step for step in remaining)


def test_the_command_line_on_the_current_snapshot_is_empty_and_writes_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End to end, every golden case, and the vendored directory byte-identical afterwards."""
    before = _vendor_digests()
    assert revendor.main(["--from-dir", str(OSCAL)]) == 0
    out = capsys.readouterr().out
    published = len(load_metaschema().constraints)
    assert f"constraints published: {published} -> {published}" in out
    assert "files whose bytes differ: 0" in out
    assert "0 would move" in out
    assert _vendor_digests() == before


# -- the command line's other paths ------------------------------------------


def test_cached_goldens_that_are_absent_are_counted_not_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run CI makes: no cache. Eight cases are named as not run, not left out."""
    monkeypatch.setattr(revendor, "CACHE", tmp_path / "no-cache")
    _, impact = _impact(_candidate(tmp_path))
    assert impact["cases_not_run"] == [name for name, _ in CACHED]
    assert impact["cases_run"] == len(CASES)
    assert impact["moved"] == []


class _Release:
    """A fetcher that serves the vendored bytes and records every URL it was asked for."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def fetch(self, url: str) -> Any:
        from types import SimpleNamespace

        self.urls.append(url)
        published = url.rsplit("/", 1)[1]
        vendored = next(n for n in revendor.NAMES if revendor.original_name(n) == published)
        return SimpleNamespace(
            body=(OSCAL / vendored).read_bytes(), final_url=url, fetched_at="2026-09-11T00:00:00Z"
        )


def test_the_command_line_fetches_every_file_by_the_name_nist_publishes_it_under(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``complete_schema.json`` was renamed on the way in.

    NIST's release still publishes it as ``oscal_complete_schema.json``, and the
    fetch has to ask for that name.
    """
    monkeypatch.setattr(revendor, "CACHED", [])
    release = _Release()
    assert revendor.main(["9.9.9"], fetcher=release) == 0
    assert len(release.urls) == len(revendor.NAMES)
    base = "https://github.com/usnistgov/OSCAL/releases/download/v9.9.9/"
    assert f"{base}oscal_complete_schema.json" in release.urls
    assert f"{base}complete_schema.json" not in release.urls
    assert "files whose bytes differ: 0" in capsys.readouterr().out


def test_the_json_output_is_the_same_diff(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(revendor, "CACHED", [])
    assert revendor.main(["--from-dir", str(OSCAL), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["change"]["files"]["changed"] == []
    assert payload["change"]["constraints"]["published"]["from"] == len(
        load_metaschema().constraints
    )
    assert payload["goldens"]["moved"] == []
    assert len(payload["files"]) == len(revendor.NAMES)


def test_the_command_line_writes_only_with_write_and_only_where_it_is_told(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(revendor, "CACHED", [])
    vendor = tmp_path / "vendor"
    shutil.copytree(VENDOR, vendor)
    monkeypatch.setattr(revendor, "VENDOR", vendor)
    real_before = _vendor_digests()
    directory = _candidate(tmp_path)
    _edit(
        directory / CATALOG,
        '<index id="oscal-catalog-controls"',
        '<index id="oscal-catalog-controls" level="WARNING"',
    )
    assert revendor.main(["--from-dir", str(directory)]) == 1
    assert _digest(vendor / "oscal" / CATALOG) == _digest(OSCAL / CATALOG), "a dry run wrote"
    assert revendor.main(["--from-dir", str(directory), "--write"]) == 1
    assert _digest(vendor / "oscal" / CATALOG) == _digest(directory / CATALOG)
    assert "Still to do by hand" in capsys.readouterr().err
    assert _vendor_digests() == real_before, "the real vendored directory moved"


def test_a_missing_hash_row_refuses_the_write_before_any_byte_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(revendor, "CACHED", [])
    vendor = tmp_path / "vendor"
    shutil.copytree(VENDOR, vendor)
    sources = vendor / "SOURCES.md"
    lines = sources.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [line for line in lines if f"`oscal/{CATALOG}`" not in line]
    assert len(kept) == len(lines) - 1, "the row to remove was not found exactly once"
    sources.write_text("".join(kept), encoding="utf-8")
    monkeypatch.setattr(revendor, "VENDOR", vendor)
    before = {path.name: _digest(path) for path in (vendor / "oscal").iterdir()}
    directory = _candidate(tmp_path)
    _edit(
        directory / CATALOG,
        '<index id="oscal-catalog-controls"',
        '<index id="oscal-catalog-controls" level="WARNING"',
    )
    assert revendor.main(["--from-dir", str(directory), "--write"]) == 2
    assert "hash row" in capsys.readouterr().err
    assert {path.name: _digest(path) for path in (vendor / "oscal").iterdir()} == before
