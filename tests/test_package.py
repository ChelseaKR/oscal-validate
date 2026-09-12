"""``oscal-validate package``: N runs of the command line, plus what only a set shows.

Three properties carry this file.

**Each member's report is the command line's.** Package mode validates every
member with every other member as its resolve set, through the same
composition function ``oscal-validate <member> --resolve <directory>``
reaches. So the comparison below is byte for byte, in both formats and both
settings of ``--locations``, over a member set read from the directory rather
than typed here.

**It fails closed, and an empty or unreadable package is never a report.** A
file that cannot be read makes the whole run exit 2 with nothing on stdout,
naming every such file: a report with a short document list is exactly what a
smaller clean package looks like, and validating the rest would publish
``IMPORT_NOT_SUPPLIED`` about a file that was supplied.

**Every cross-document section is witnessed populated and empty.** A section
proven only empty is a statement about the fixture, and a section that could
never populate is a check that cannot fail; #60's ambiguous-imports section
was the second kind and is absent for that reason (see ``package.py``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from oscal_validate.checks.identifiers import uuid_definitions
from oscal_validate.cli import DETERMINISTIC_COMMANDS
from oscal_validate.cli import main as cli_main
from oscal_validate.package import (
    NOTES,
    PACKAGE_SCHEMA_PATH,
    PACKAGE_SCHEMA_VERSION,
    PackageError,
    Unreadable,
    read_package,
    read_package_schema,
)
from oscal_validate.report import read_report_schema

from .conftest import fixture_path
from .schema_check import check

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "tests" / "fixtures" / "package"
PACKAGE_SCHEMA: dict[str, Any] = json.loads(read_package_schema())
REPORT_SCHEMA: dict[str, Any] = json.loads(read_report_schema())

#: The codes that say an import or a reference into one was not settled.
UNSETTLED = frozenset({"IMPORT_NOT_SUPPLIED", "IMPORT_AMBIGUOUS", "REFERENCE_UNVERIFIABLE"})


def _members(directory: Path) -> list[Path]:
    return sorted(path for path in directory.iterdir() if path.suffix == ".json")


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = cli_main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "package"
    shutil.copytree(PACKAGE, target)
    return target


def _json_report(directory: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    code, out, err = _run(["package", str(directory), "--format", "json"], capsys)
    assert code in (0, 1), err
    report: dict[str, Any] = json.loads(out)
    return report


def _text_blocks(out: str) -> dict[str, str]:
    """Each member's block of a text package report, keyed by its path."""
    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in out.splitlines():
        if line == "== across the package ==":
            break
        if line.startswith("== ") and line.endswith(" =="):
            current = blocks.setdefault(line[3:-3], [])
            continue
        if current is not None:
            current.append(line)
    return {
        path: "\n".join(lines[:-1] if lines and lines[-1] == "" else lines)
        for path, lines in blocks.items()
    }


# -- the fixture is the package the issue names ------------------------------


def test_the_fixture_package_holds_the_three_models_the_issue_names() -> None:
    """A floor under everything below, read from the fixture, not typed."""
    package = read_package(PACKAGE)
    assert len(package.members) == len(_members(PACKAGE))
    assert sorted(member.model for member in package.members) == [
        "catalog",
        "profile",
        "system-security-plan",
    ]


# -- each member's report is the command line's ------------------------------


@pytest.mark.parametrize("fmt", ["json", "text"])
@pytest.mark.parametrize("locations", [False, True])
def test_every_member_s_report_is_the_bytes_the_command_line_writes(
    fmt: str, locations: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    flag = ["--locations"] if locations else []
    code, out, err = _run(["package", str(PACKAGE), "--format", fmt, *flag], capsys)
    assert code == 0, err
    members = _members(PACKAGE)
    if fmt == "json":
        documents = {entry["path"]: entry for entry in json.loads(out)["documents"]}
        served = {
            path: json.dumps(entry["report"], indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            for path, entry in documents.items()
        }
    else:
        documents = {}
        served = {path: block + "\n" for path, block in _text_blocks(out).items()}
    assert set(served) == {str(member) for member in members}, "a member is missing or extra"

    for member in members:
        cli_code, cli_out, _ = _run(
            [str(member), "--resolve", str(PACKAGE), "--format", fmt, *flag], capsys
        )
        assert served[str(member)] == cli_out, f"{member.name} ({fmt}, locations={locations})"
        if documents:
            assert documents[str(member)]["exit_code"] == cli_code


def test_a_relative_directory_reads_the_same_set_as_an_absolute_one() -> None:
    """Paths are how a member's own imports are told apart from transitive ones.

    ``positions._split`` once read every finding in an absolutely-pathed
    supporting document as a pointer into the primary one, because an absolute
    path and a pointer both begin with ``/``. Package mode selects a member's
    edges by the document they were recorded in, never by parsing a pointer;
    this runs it both ways and asserts the same graph.
    """
    command = [sys.executable, "-m", "oscal_validate", "package"]
    relative = subprocess.run(
        [*command, "tests/fixtures/package", "--format", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    absolute = subprocess.run(
        [*command, str(PACKAGE), "--format", "json"], capture_output=True, text=True, check=False
    )
    assert relative.returncode == absolute.returncode == 0, relative.stderr + absolute.stderr

    def shape(out: str) -> list[tuple[str, str]]:
        graph = json.loads(out)["import_graph"]
        return [(Path(e["from"]).name, Path(e["resolved_to"]).name) for e in graph]

    assert shape(relative.stdout) == shape(absolute.stdout)
    assert shape(relative.stdout), "the graph is empty; the comparison would be vacuous"


# -- #60's four "done when" items --------------------------------------------


def test_the_package_settles_every_import_its_members_leave_unsettled_alone(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Done when 1, from both sides: alone they are unsettled, together they are not.

    The refused case is in the same test as the accepted one. A package mode
    that settled nothing would pass an assertion that only looked at the
    package, if the fixture happened to need nothing settling.
    """
    importers = []
    for member in _members(PACKAGE):
        _, out, _ = _run([str(member), "--format", "json"], capsys)
        alone = {finding["code"] for finding in json.loads(out)["findings"]}
        if alone & UNSETTLED:
            importers.append(member.name)
    assert importers, "no member needs the package to settle anything; vacuous"

    package = read_package(PACKAGE)
    assert all(edge.resolved_to for edge in package.import_graph())
    assert package.imports_not_in_package() == ()
    for validated in package.members:
        unsettled = {finding.code for finding in validated.findings} & UNSETTLED
        assert not unsettled, f"{validated.path}: {sorted(unsettled)}"


def test_removing_the_catalog_names_it_as_not_supplied_and_never_as_a_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Done when 2: the absence is reported, by name, in both places it belongs."""
    directory = _copy(tmp_path)
    (directory / "catalog.json").unlink()
    report = _json_report(directory, capsys)

    missing = [(Path(e["from"]).name, e["href"]) for e in report["imports_not_in_package"]]
    assert missing == [("profile.json", "catalog.json")]
    assert report["summary"]["imports_not_in_package"] == 1

    profile = next(d for d in report["documents"] if d["path"].endswith("profile.json"))
    not_supplied = [
        f["value"] for f in profile["report"]["findings"] if f["code"] == "IMPORT_NOT_SUPPLIED"
    ]
    assert not_supplied == ["catalog.json"]


def test_an_empty_directory_is_exit_two_and_writes_no_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Done when 3. A package with nothing in it has not been found clean."""
    code, out, err = _run(["package", str(tmp_path), "--format", "json"], capsys)
    assert code == 2
    assert out == ""
    assert "holds no .json file" in err


def test_a_directory_holding_only_other_files_is_empty_too(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "catalog.xml").write_text("<catalog/>", encoding="utf-8")
    code, out, err = _run(["package", str(tmp_path)], capsys)
    assert (code, out) == (2, "")
    assert "holds no .json file" in err


def test_a_path_that_is_not_a_directory_is_exit_two(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(["package", str(fixture_path("clean_catalog.json"))], capsys)
    assert (code, out) == (2, "")
    assert "is not a directory" in err


def test_the_same_bytes_every_run_whatever_order_the_directory_lists_in(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Done when 4, with the reversal asserted to have landed.

    A monkeypatch that silently did nothing would leave this passing for the
    wrong reason, so the reversed listing is checked before it is relied on.
    """
    first = _run(["package", str(PACKAGE), "--format", "json"], capsys)[1]
    assert _run(["package", str(PACKAGE), "--format", "json"], capsys)[1] == first

    listed = [path.name for path in PACKAGE.iterdir()]
    original = Path.iterdir

    def reversed_listing(self: Path) -> Any:
        return iter(sorted(original(self), reverse=True))

    monkeypatch.setattr(Path, "iterdir", reversed_listing)
    assert [path.name for path in PACKAGE.iterdir()] == sorted(listed, reverse=True)
    assert [path.name for path in PACKAGE.iterdir()] != sorted(listed)
    assert _run(["package", str(PACKAGE), "--format", "json"], capsys)[1] == first


def test_the_same_bytes_across_processes_and_hash_seeds() -> None:
    outputs = []
    for seed in ("0", "1"):
        run = subprocess.run(
            [sys.executable, "-m", "oscal_validate", "package", str(PACKAGE), "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        assert run.returncode == 0, run.stderr
        outputs.append(run.stdout)
    assert outputs[0] == outputs[1]


# -- it fails closed ---------------------------------------------------------


def test_a_member_that_is_not_oscal_fails_the_package_closed_and_is_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _copy(tmp_path)
    (directory / "package.json").write_text('{"name": "not-oscal"}', encoding="utf-8")
    code, out, err = _run(["package", str(directory), "--format", "json"], capsys)
    assert code == 2
    assert out == "", "a report with a short document list reads as a smaller clean package"
    assert f"1 of {len(_members(directory))} file(s)" in err
    assert "package.json: no OSCAL model root found" in err


def test_every_member_that_cannot_be_read_is_named_not_only_the_first(tmp_path: Path) -> None:
    """Two different reasons, both named, and the denominator is the directory's."""
    directory = _copy(tmp_path)
    (directory / "a-notes.json").write_text("{ not json", encoding="utf-8")
    (directory / "b-other.json").write_text('{"name": "not-oscal"}', encoding="utf-8")
    with pytest.raises(Unreadable) as refused:
        read_package(directory)
    named = {Path(item.path).name: item.reason for item in refused.value.unread}
    assert set(named) == {"a-notes.json", "b-other.json"}
    assert "not valid JSON" in named["a-notes.json"]
    assert "no OSCAL model root found" in named["b-other.json"]
    assert refused.value.examined == len(_members(directory))


@pytest.mark.parametrize("depth", [4000, 100_000])
def test_a_member_too_deep_to_walk_fails_the_package_closed_not_with_a_traceback(
    depth: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2 and the member's name, the way the command line refuses it.

    Found building this. At 4,000 levels the decoder reads the file and the
    constraint layer's descendant walk is what recurses, so guarding only the
    read let it escape as a traceback with exit code 1 -- the code this tool
    reserves for an ERROR it found. At 100,000 levels the decoder itself gives
    up. Both are the command line's exit 2, and both are driven here.
    """
    directory = _copy(tmp_path)
    deep = directory / "deep.json"
    deep.write_text('{"catalog": ' + "[" * depth + "]" * depth + "}", encoding="utf-8")
    code, out, err = _run(["package", str(directory)], capsys)
    assert code == 2
    assert out == ""
    assert f"{deep} nests too deeply to read safely" in err

    cli_code, _, cli_err = _run([str(deep)], capsys)
    assert cli_code == 2
    assert "nests too deeply to read safely" in cli_err


def test_read_package_refuses_rather_than_returning_an_empty_package(tmp_path: Path) -> None:
    with pytest.raises(PackageError):
        read_package(tmp_path)
    with pytest.raises(PackageError):
        read_package(tmp_path / "absent")


# -- the verdict is the command line's --------------------------------------


def test_an_error_in_any_member_is_exit_one_and_the_member_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copy(fixture_path("broken_catalog.json"), tmp_path / "broken.json")
    code, out, err = _run(["package", str(tmp_path), "--format", "json"], capsys)
    assert code == 1, err
    report = json.loads(out)
    assert [d["exit_code"] for d in report["documents"]] == [1]
    assert report["summary"]["ERROR"] == report["documents"][0]["report"]["summary"]["ERROR"] > 0


def test_the_cross_document_sections_never_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A package whose only news is cross-document still exits 0."""
    directory = _copy(tmp_path)
    (directory / "catalog.json").unlink()
    code, _, _ = _run(["package", str(directory)], capsys)
    assert code == 0


# -- the cross-document sections, populated and empty ------------------------


def test_the_import_graph_is_each_member_s_own_imports_and_nothing_transitive() -> None:
    """The SSP reaches the catalog through the profile; that edge is the profile's."""
    graph = read_package(PACKAGE).import_graph()
    edges = [(Path(e.source).name, Path(e.resolved_to or "").name, e.matched_by) for e in graph]
    assert edges == [
        ("profile.json", "catalog.json", "file name"),
        ("ssp.json", "profile.json", "file name"),
    ]


def test_an_import_matched_by_stem_says_so(tmp_path: Path) -> None:
    """The second of the two matching rules, which the fixture alone never takes."""
    directory = _copy(tmp_path)
    profile_path = directory / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["profile"]["imports"][0]["href"] = "catalog.xml"
    profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    graph = read_package(directory).import_graph()
    stem = [e for e in graph if Path(e.source).name == "profile.json"]
    assert [(e.href, Path(e.resolved_to or "").name, e.matched_by) for e in stem] == [
        ("catalog.xml", "catalog.json", "file name without extension")
    ]


def test_unreferenced_names_the_roots_and_nothing_imported() -> None:
    assert [Path(path).name for path in read_package(PACKAGE).unreferenced()] == ["ssp.json"]


def test_a_member_nothing_imports_is_its_own_root(tmp_path: Path) -> None:
    shutil.copy(fixture_path("clean_catalog.json"), tmp_path / "alone.json")
    assert [Path(p).name for p in read_package(tmp_path).unreferenced()] == ["alone.json"]


def test_the_clean_package_declares_no_uuid_twice() -> None:
    assert read_package(PACKAGE).uuid_collisions() == ()


def test_one_uuid_declared_in_two_members_is_one_collision_naming_both(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exactly one, at exactly the two places, and the run still exits 0."""
    directory = _copy(tmp_path)
    catalog = read_package(directory).members[0]
    assert Path(catalog.path).name == "catalog.json"
    shared = next(uuid_definitions(catalog.document.walked))

    ssp_path = directory / "ssp.json"
    ssp = json.loads(ssp_path.read_text(encoding="utf-8"))
    ssp["system-security-plan"]["uuid"] = shared.value
    ssp_path.write_text(json.dumps(ssp, indent=2), encoding="utf-8")

    report = _json_report(directory, capsys)
    assert report["summary"]["uuid_collisions"] == 1
    [collision] = report["uuid_collisions"]
    assert collision["uuid"] == shared.value
    assert [(Path(d["path"]).name, d["location"]) for d in collision["declared_at"]] == [
        ("catalog.json", shared.pointer),
        ("ssp.json", "/system-security-plan/uuid"),
    ]
    assert all(d["exit_code"] == 0 for d in report["documents"])


def test_a_uuid_duplicated_inside_one_member_is_its_error_not_a_collision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Inside one document it is check 4's ERROR; across documents it is package policy.

    Two different claims with two different severities. A collision section
    that also counted a duplicate inside one file would report one defect
    twice, under two rules, and the fixture package alone could never show it.
    """
    directory = _copy(tmp_path)
    ssp_path = directory / "ssp.json"
    ssp = json.loads(ssp_path.read_text(encoding="utf-8"))
    plan = ssp["system-security-plan"]
    component = plan["system-implementation"]["components"][0]
    plan["control-implementation"]["implemented-requirements"][0]["uuid"] = component["uuid"]
    ssp_path.write_text(json.dumps(ssp, indent=2), encoding="utf-8")

    report = _json_report(directory, capsys)
    assert report["uuid_collisions"] == []
    ssp_report = next(d for d in report["documents"] if d["path"].endswith("ssp.json"))
    duplicated = [f for f in ssp_report["report"]["findings"] if f["code"] == "UUID_NOT_UNIQUE"]
    assert [f["value"] for f in duplicated] == [component["uuid"]]
    assert ssp_report["exit_code"] == 1


# -- the published shape -----------------------------------------------------


def test_the_package_report_conforms_and_so_does_every_embedded_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _json_report(PACKAGE, capsys)
    assert check(report, PACKAGE_SCHEMA) == []
    assert report["documents"], "no embedded report to check; vacuous"
    for document in report["documents"]:
        assert check(document["report"], REPORT_SCHEMA) == [], document["path"]
    assert report["notes"] == NOTES


def test_the_schema_s_version_is_the_one_reports_carry(capsys: pytest.CaptureFixture[str]) -> None:
    const = PACKAGE_SCHEMA["properties"]["package_report_schema_version"]["const"]
    assert const == PACKAGE_SCHEMA_VERSION
    assert _json_report(PACKAGE, capsys)["package_report_schema_version"] == const


def test_the_schema_refuses_a_report_with_no_documents(capsys: pytest.CaptureFixture[str]) -> None:
    """``minItems`` is enforced, not merely listed.

    A package report exists only once a member has been read.
    """
    report = _json_report(PACKAGE, capsys)
    report["documents"] = []
    assert any("fewer than minItems 1" in error for error in check(report, PACKAGE_SCHEMA))


def test_the_schema_refuses_a_collision_declared_once(capsys: pytest.CaptureFixture[str]) -> None:
    report = _json_report(PACKAGE, capsys)
    report["uuid_collisions"] = [{"uuid": "x", "declared_at": [{"path": "a", "location": "/"}]}]
    assert any("fewer than minItems 2" in error for error in check(report, PACKAGE_SCHEMA))


def test_the_schema_ships_as_package_data_and_the_verb_prints_it() -> None:
    listed = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"package.schema.json"' in listed, "package-data no longer ships the package schema"
    printed = subprocess.run(
        [sys.executable, "-m", "oscal_validate", "package", "--report-schema"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert printed.returncode == 0, printed.stderr
    assert printed.stdout == PACKAGE_SCHEMA_PATH.read_text(encoding="utf-8")


# -- wiring ------------------------------------------------------------------


def test_the_top_level_command_returns_the_verb_s_own_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A call that comes back through the dispatch branch rather than exiting in argparse."""
    code, _, err = _run(["package", str(tmp_path / "absent")], capsys)
    assert code == 2
    assert "is not a directory" in err


def test_the_action_has_no_package_mode_yet_and_the_help_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When the Action gains package mode, this fails until the help stops denying it."""
    action = (ROOT / "action.yml").read_text(encoding="utf-8")
    inputs = action.split("\ninputs:\n", 1)[1].split("\noutputs:\n", 1)[0]
    declared = [
        line.strip().rstrip(":")
        for line in inputs.splitlines()
        if line.startswith("  ") and not line.startswith("   ") and line.strip().endswith(":")
    ]
    assert declared, "no inputs read from action.yml; the assertion below would be vacuous"
    assert "mode" not in declared
    with pytest.raises(SystemExit):
        cli_main(["package", "--help"])
    assert "The GitHub Action does not run this verb yet" in " ".join(
        capsys.readouterr().out.split()
    )


def test_the_pre_commit_hook_runs_the_package_verb_on_a_directory() -> None:
    hooks = (ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    entries = [
        line.split(":", 1)[1].strip()
        for line in hooks.splitlines()
        if line.strip().startswith("entry:")
    ]
    assert entries == ["oscal-validate package"]
    script, verb = entries[0].split()
    assert verb in DETERMINISTIC_COMMANDS
    assert f'{script} = "oscal_validate.cli:entrypoint"' in (ROOT / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert "pass_filenames: false" in hooks, "a list of changed files is not a directory"
