"""The MCP server answers with the validator's own bytes, and refuses the rest.

Three properties carry this file, and each has a control recorded in the pull
request that added it.

**The report is the validator's.** ``validate`` does not summarise, re-order or
re-serialise anything: the report it returns is the exact document
``--format json`` writes, compared here byte for byte for every fixture and
for both settings of ``--locations``. An assistant that quotes a finding is
quoting this tool.

**A refusal is an answer.** A document that cannot be read comes back as a
refusal carrying exit-2 semantics, never as a report with an empty findings
list -- an empty findings list is what a *clean* document looks like, and
collapsing the two is the defect this project exists to report. The same goes
for a path outside the root, an unknown tool and an identifier that names no
rule.

**The disclosures are derived, not restated.** ``coverage``'s counts come from
the same parse the validator runs, ``limits`` serves a file generated from the
README, and the vocabulary the server refuses judgments on is held against
``ai/guard.py``'s. Every one of those could be a second, weaker copy of
something; each is pinned to its source in both directions instead.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from oscal_validate import __version__
from oscal_validate.ai import guard
from oscal_validate.cli import main as cli_main
from oscal_validate.limits import LIMITS_PATH, read_limits
from oscal_validate.mcp import (
    BOUNDARY,
    HANDLERS,
    JUDGMENT_VOCABULARY,
    PROTOCOL_VERSION,
    SERVER_INFO,
    TOOLS,
    OutsideRoot,
    call_tool,
    handle,
    is_judgment_request,
    main,
    serve,
    within,
)
from oscal_validate.metaschema import load_metaschema
from oscal_validate.rule import main as rule_main

from .conftest import fixture_path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
README = ROOT / "README.md"


def _payload(result: dict[str, Any]) -> Any:
    """The JSON a tool answered with, out of the MCP content envelope."""
    content = result["content"]
    assert len(content) == 1 and content[0]["type"] == "text"
    return json.loads(content[0]["text"])


def _call(root: Path, name: str, **arguments: Any) -> Any:
    return _payload(call_tool(root, name, arguments))


def _request(identifier: int, name: str, arguments: dict[str, Any]) -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": identifier,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )


# -- the protocol surface ----------------------------------------------------


def test_initialize_reports_the_protocol_and_this_package_s_version() -> None:
    answer = handle(ROOT, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert answer is not None
    assert answer["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert answer["result"]["serverInfo"] == SERVER_INFO
    # Derived from the package rather than typed into the server, so a release
    # cannot leave a client being told a version that was never cut.
    assert SERVER_INFO["version"] == __version__


def test_every_advertised_tool_has_a_handler_and_every_handler_is_advertised() -> None:
    """Both directions, because either half alone permits a lie.

    A tool advertised with no handler is a client calling something that
    refuses; a handler nobody advertises is a surface no reader of
    ``tools/list`` knows exists.
    """
    advertised = {tool["name"] for tool in TOOLS}
    assert advertised, "an empty tool list would make everything below vacuous"
    assert advertised == set(HANDLERS)
    for tool in TOOLS:
        assert tool["description"].strip()
        assert tool["inputSchema"]["type"] == "object"


def test_tools_list_is_what_the_module_advertises() -> None:
    answer = handle(ROOT, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert answer is not None
    assert answer["result"]["tools"] == TOOLS


def test_an_unknown_method_is_an_error_and_a_notification_is_silence() -> None:
    answer = handle(ROOT, {"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
    assert answer is not None
    assert answer["error"]["code"] == -32601
    assert handle(ROOT, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


@pytest.mark.parametrize("method", ["initialize", "tools/list", "tools/call"])
def test_a_method_this_server_implements_still_answers_nothing_without_an_id(
    method: str,
) -> None:
    """A JSON-RPC notification takes no reply, even for a method that works.

    The id-less case is easy to get right for the method that falls through
    and wrong for the three that produce a result: the answer is computed
    either way, and the question is whether it is written. Driven through
    ``serve`` as well, because a reply the loop suppresses and a reply the
    loop writes are the same object one line earlier.
    """
    request = {"jsonrpc": "2.0", "method": method, "params": {"name": "limits", "arguments": {}}}
    assert handle(ROOT, request) is None
    assert _serve_lines(ROOT, json.dumps(request)) == []


def test_an_unreadable_line_is_a_parse_error_and_the_server_keeps_going() -> None:
    """A bad request must not take the session down with it."""
    lines = "\n".join(
        [
            "this is not json",
            "",
            _request(7, "limits", {}),
        ]
    )
    out = _serve_lines(ROOT, lines)
    assert len(out) == 2
    assert out[0]["error"]["code"] == -32700
    assert out[0]["id"] is None
    assert out[1]["id"] == 7


def test_an_exception_inside_a_handler_is_reported_against_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setitem(HANDLERS, "limits", explode)
    out = _serve_lines(ROOT, _request(11, "limits", {}))
    assert out[0]["id"] == 11
    assert out[0]["error"]["code"] == -32603
    assert "RuntimeError: boom" in out[0]["error"]["message"]


def _serve_lines(root: Path, lines: str) -> list[dict[str, Any]]:
    import io

    sink = io.StringIO()
    assert serve(root, io.StringIO(lines + "\n"), sink) == 0
    return [json.loads(line) for line in sink.getvalue().splitlines() if line.strip()]


# -- validate: the report is the validator's, byte for byte ------------------

DOCUMENTS = [
    "clean_catalog.json",
    "broken_catalog.json",
    "clean_profile.json",
    "clean_mapping_collection.json",
    "nist_ssp_example.json",
]


@pytest.mark.parametrize("document", DOCUMENTS)
@pytest.mark.parametrize("locations", [False, True])
def test_validate_returns_the_bytes_the_command_line_writes(
    document: str, locations: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    path = fixture_path(document)
    argv = [str(path), "--format", "json"] + (["--locations"] if locations else [])
    expected_exit = cli_main(argv)
    expected = capsys.readouterr().out

    answered = _call(FIXTURES, "validate", path=document, locations=locations)
    assert answered["outcome"] == "validated"
    assert answered["exit_code"] == expected_exit
    served = json.dumps(answered["report"], indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert served == expected, f"{document} (locations={locations}) is not the CLI's report"


def test_resolve_reaches_the_import_and_its_absence_is_reported_not_hidden() -> None:
    """The one thing --resolve changes, from both sides."""
    alone = _call(FIXTURES, "validate", path="clean_profile.json")
    codes = {finding["code"] for finding in alone["report"]["findings"]}
    assert "IMPORT_NOT_SUPPLIED" in codes
    assert alone["report"]["summary"]["UNVERIFIABLE"] > 0

    supplied = _call(
        FIXTURES, "validate", path="clean_profile.json", resolve=["clean_catalog.json"]
    )
    resolved = {finding["code"] for finding in supplied["report"]["findings"]}
    assert "IMPORT_NOT_SUPPLIED" not in resolved
    assert "IMPORT_RESOLVED" in resolved


def test_a_document_that_cannot_be_read_is_a_refusal_carrying_exit_two(
    tmp_path: Path,
) -> None:
    """Never an empty findings list: that is what a clean document looks like."""
    broken = tmp_path / "not-json.json"
    broken.write_text("{ this is not json", encoding="utf-8")
    answered = _call(tmp_path.resolve(), "validate", path="not-json.json")
    assert answered["outcome"] == "refused"
    assert answered["exit_code"] == 2
    assert "report" not in answered
    assert "not valid JSON" in answered["reason"]


def test_a_document_that_is_not_there_is_a_refusal_naming_it(tmp_path: Path) -> None:
    answered = _call(tmp_path.resolve(), "validate", path="absent.json")
    assert answered["outcome"] == "refused"
    assert answered["exit_code"] == 2
    assert "absent.json" in answered["reason"]


def test_a_document_that_nests_too_deeply_is_refused_the_way_the_cli_refuses_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The last of the three ways a run can end at exit 2, and both doors agree.

    4,000 nested arrays is past any interpreter's recursion limit, so the
    decoder gives up before the walk begins. What matters is that giving up
    is reported as giving up: this is the branch that, mishandled, publishes
    a document nobody could read as a document with nothing wrong in it.
    """
    deep = tmp_path / "deep.json"
    depth = 4000
    deep.write_text('{"catalog": ' + "[" * depth + "]" * depth + "}", encoding="utf-8")

    assert cli_main([str(deep)]) == 2
    assert "nests too deeply" in capsys.readouterr().err

    answered = _call(tmp_path.resolve(), "validate", path="deep.json")
    assert answered["outcome"] == "refused"
    assert answered["exit_code"] == 2
    assert "nests too deeply" in answered["reason"]
    assert "report" not in answered


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({}, "needs 'path'"),
        ({"path": "   "}, "needs 'path'"),
        ({"path": "clean_catalog.json", "resolve": "clean_catalog.json"}, "must be a list"),
        ({"path": "clean_catalog.json", "resolve": [1]}, "must be a list"),
    ],
)
def test_validate_refuses_arguments_it_cannot_read(
    arguments: dict[str, Any], expected: str
) -> None:
    answered = _payload(call_tool(FIXTURES, "validate", arguments))
    assert answered["outcome"] == "refused"
    assert expected in answered["reason"]


# -- the root ----------------------------------------------------------------


def test_a_path_outside_the_root_is_refused_and_names_both(tmp_path: Path) -> None:
    root = (tmp_path / "root").resolve()
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"catalog": {}}', encoding="utf-8")
    answered = _call(root, "validate", path="../outside.json")
    assert answered["outcome"] == "refused"
    assert answered["exit_code"] == 2
    assert str(root) in answered["reason"]
    assert "outside this server's root" in answered["reason"]


def test_a_resolve_path_outside_the_root_is_refused_too(tmp_path: Path) -> None:
    """The guard has to cover every path a tool takes, not only the first one."""
    root = (tmp_path / "root").resolve()
    root.mkdir()
    (root / "clean.json").write_text(
        fixture_path("clean_catalog.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "elsewhere.json").write_text('{"catalog": {}}', encoding="utf-8")
    answered = _call(root, "validate", path="clean.json", resolve=["../elsewhere.json"])
    assert answered["outcome"] == "refused"
    assert "elsewhere.json" in answered["reason"]


def test_a_symlink_out_of_the_root_is_refused_rather_than_followed(tmp_path: Path) -> None:
    """The question is which bytes get read, not which name was typed."""
    root = (tmp_path / "root").resolve()
    root.mkdir()
    target = tmp_path / "secret.json"
    target.write_text('{"catalog": {}}', encoding="utf-8")
    (root / "innocent.json").symlink_to(target)
    with pytest.raises(OutsideRoot) as refused:
        within(root, "innocent.json")
    assert str(target.resolve()) in str(refused.value)


def test_an_absolute_path_inside_the_root_is_accepted(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    document = root / "clean.json"
    document.write_text(
        fixture_path("clean_catalog.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert within(root, str(document)) == document
    answered = _call(root, "validate", path=str(document))
    assert answered["outcome"] == "validated"


def test_the_root_itself_is_inside_the_root(tmp_path: Path) -> None:
    """A directory of documents is a legitimate --resolve argument."""
    root = tmp_path.resolve()
    assert within(root, ".") == root


def test_a_root_that_is_not_a_directory_is_refused_before_anything_is_served(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nowhere"
    assert main(["mcp", "--root", str(missing)]) == 2
    assert "is not a directory" in capsys.readouterr().err


def test_the_mcp_verb_is_dispatched_by_the_top_level_cli() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli_main(["mcp", "--help"])
    assert exit_info.value.code == 0


def test_the_top_level_cli_returns_the_server_s_own_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--help`` exits through argparse and never reaches the return.

    So the dispatch branch's own ``return`` needs a call that comes back
    rather than raising, or the one line joining the verb to the top-level
    command is never executed by anything.
    """
    assert cli_main(["mcp", "--root", str(tmp_path / "nowhere")]) == 2
    assert "is not a directory" in capsys.readouterr().err


def test_the_verb_serves_a_request_on_real_stdin_as_a_launched_process() -> None:
    """The way a client actually starts it: a process, a pipe, an answer.

    Everything above drives ``serve`` with string buffers. This is the only
    test that proves ``oscal-validate mcp`` reads the process's own stdin and
    writes the answer to the process's own stdout -- the two lines that a
    client meets first and that no in-process test touches.
    """
    request = _request(1, "validate", {"path": "clean_catalog.json"})
    result = subprocess.run(
        [sys.executable, "-m", "oscal_validate", "mcp", "--root", str(FIXTURES)],
        input=request + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    answered = json.loads(json.loads(result.stdout)["result"]["content"][0]["text"])
    assert answered["outcome"] == "validated"
    assert answered["exit_code"] == 0


# -- rule --------------------------------------------------------------------


@pytest.mark.parametrize("identifier", ["REFERENCE_UNVERIFIABLE", "oscal-catalog-controls"])
def test_rule_answers_exactly_what_the_rule_verb_prints(
    identifier: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two front doors onto one citation trail; they must not diverge."""
    assert rule_main(["rule", identifier, "--format", "json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert _call(ROOT, "rule", identifier=identifier) == printed


def test_rule_refuses_an_identifier_that_names_nothing() -> None:
    answered = _call(ROOT, "rule", identifier="not-a-constraint")
    assert answered["outcome"] == "refused"
    assert "not-a-constraint" in answered["reason"]
    assert answered["constraint_identifiers"].endswith("CONSTRAINT-COVERAGE.md")


def test_rule_refuses_a_missing_identifier() -> None:
    answered = _payload(call_tool(ROOT, "rule", {}))
    assert answered["outcome"] == "refused"
    assert "needs 'identifier'" in answered["reason"]


# -- coverage ----------------------------------------------------------------


def test_coverage_counts_come_from_the_same_parse_the_validator_runs() -> None:
    metaschema = load_metaschema()
    answered = _call(ROOT, "coverage")
    assert answered["published"] == len(metaschema.constraints)
    assert answered["evaluated"] == len(metaschema.evaluated())
    assert answered["matched"] == len(metaschema.constraints)
    assert len(answered["constraints"]) == answered["matched"]
    assert sum(row["published"] for row in answered["by_kind"]) == answered["published"]
    assert sum(row["evaluated"] for row in answered["by_kind"]) == answered["evaluated"]


def test_coverage_agrees_with_the_published_table() -> None:
    """The generated document and the served answer are one measurement.

    ``docs/CONSTRAINT-COVERAGE.md`` is itself held to the vendored files by
    ``tests/test_constraint_coverage.py``, so this ties the tool to the same
    anchor by a different route: the sentence a reader sees on the page.
    """
    answered = _call(ROOT, "coverage")
    table = (ROOT / "docs" / "CONSTRAINT-COVERAGE.md").read_text(encoding="utf-8")
    sentence = (
        f"{answered['evaluated']} of {answered['published']} published constraints are evaluated."
    )
    assert sentence in table


def test_every_constraint_the_release_publishes_has_a_row_with_a_verdict() -> None:
    answered = _call(ROOT, "coverage")
    for row in answered["constraints"]:
        assert isinstance(row["evaluated"], bool)
        if row["evaluated"]:
            assert row["level"]
        else:
            assert row["not_evaluated_because"], row["identifier"]


def test_coverage_filters_report_their_own_denominator() -> None:
    """A filtered answer must not be able to read as the whole table."""
    whole = _call(ROOT, "coverage")
    matches = _call(ROOT, "coverage", kind="matches")
    assert matches["filters"] == {"kind": "matches", "evaluated": None}
    assert 0 < matches["matched"] < whole["matched"]
    assert matches["published"] == whole["published"]
    assert {row["kind"] for row in matches["constraints"]} == {"matches"}

    skipped = _call(ROOT, "coverage", evaluated=False)
    assert skipped["matched"] == whole["published"] - whole["evaluated"]
    assert not any(row["evaluated"] for row in skipped["constraints"])


def test_coverage_refuses_a_kind_the_release_does_not_publish() -> None:
    answered = _call(ROOT, "coverage", kind="not-a-kind")
    assert answered["outcome"] == "refused"
    assert "matches" in answered["kinds_published"]


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [({"kind": 3}, "must be a constraint kind"), ({"evaluated": "yes"}, "must be true or false")],
)
def test_coverage_refuses_arguments_it_cannot_read(
    arguments: dict[str, Any], expected: str
) -> None:
    answered = _payload(call_tool(ROOT, "coverage", arguments))
    assert answered["outcome"] == "refused"
    assert expected in answered["reason"]


def test_coverage_publishes_the_lookups_that_can_never_reach_an_answer() -> None:
    """An evaluated constraint reading an index nothing builds is not coverage.

    The floor is the vendored release's own answer rather than a number typed
    here: if the derivation stopped finding them the list would be empty, and
    an empty list is exactly what "there are none" looks like.
    """
    stranded = load_metaschema().stranded_index_lookups()
    assert stranded, "the vendored release has a stranded lookup; the derivation lost it"
    answered = _call(ROOT, "coverage")
    published = answered["reading_an_index_that_is_never_built"]
    assert [row["identifier"] for row in published] == [c.identifier for c, _ in stranded]
    assert [row["populated_by"] for row in published] == [source for _, source in stranded]
    for row in published:
        assert row["reads_index"]


def test_the_coverage_note_never_lets_a_clean_run_mean_conformance() -> None:
    note = _call(ROOT, "coverage")["note"]
    assert "neither passed nor failed" in note.lower()
    assert "may still violate" in note


# -- limits ------------------------------------------------------------------


def _generated_limits() -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "limits_data.py"), "/dev/stdout"],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.rsplit("wrote /dev/stdout", 1)[0]


def test_the_packaged_limits_are_what_the_readme_says_today() -> None:
    """The staleness gate. ``make limits-data`` regenerates it."""
    assert LIMITS_PATH.read_text(encoding="utf-8") == _generated_limits()


def test_the_limits_ship_as_package_data() -> None:
    listed = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"limits.json"' in listed, "package-data no longer ships the limits"
    assert LIMITS_PATH.is_file()


def test_the_packaged_limits_are_every_limit_the_readme_publishes() -> None:
    """Counted a second way, so a reader that silently dropped one is caught.

    ``tools/limits_data.py`` splits the section into paragraphs; this counts
    the bold lead-ins by line. Two readings of one section that disagree is
    the whole signal, and neither number is written down here.
    """
    section = README.read_text(encoding="utf-8").split("\n## Limits\n", 1)[1].split("\n## ", 1)[0]
    leads = [line for line in section.splitlines() if line.startswith("**")]
    published = read_limits()
    assert leads, "no bold lead-in found; the reader, not the README, is what changed"
    assert len(published["limits"]) == len(leads)
    for entry in published["limits"]:
        assert entry["title"] in section
        assert entry["text"].startswith(f"**{entry['title']}**")


def test_a_limits_file_carrying_nothing_is_refused_rather_than_served(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty disclosure is the worst possible answer, so it is not one.

    A generator that stopped matching would write ``"limits": []``, and a
    reader that shrugged would tell an assistant this tool has no stated
    limits -- which reads as a stronger claim than the truth, not a weaker
    one.
    """
    empty = tmp_path / "limits.json"
    empty.write_text(json.dumps({"source": "", "preamble": "", "limits": []}), encoding="utf-8")
    monkeypatch.setattr("oscal_validate.limits.LIMITS_PATH", empty)
    with pytest.raises(ValueError, match="carries no limits"):
        read_limits()


def test_the_limits_tool_serves_every_limit_whole() -> None:
    answered = _call(ROOT, "limits")
    published = read_limits()
    assert answered["limits"] == published["limits"]
    assert answered["preamble"] == published["preamble"]
    assert "does not assess systems" in answered["boundary"]
    assert set(answered["severities"]) == {"ERROR", "WARNING", "INFO", "UNVERIFIABLE"}
    assert "Never a pass" in answered["severities"]["UNVERIFIABLE"]


def test_what_a_clean_run_means_carries_the_measured_denominator() -> None:
    metaschema = load_metaschema()
    sentence = _call(ROOT, "limits")["a_clean_run_means"]
    assert f"{len(metaschema.evaluated())} of {len(metaschema.constraints)}" in sentence
    assert "does not mean the other constraints passed" in sentence


# -- the boundary ------------------------------------------------------------

#: Probe sentences handed to the guard. The second is needed because an
#: outcome such as ``authorization`` is a judgment when it is *received*, not
#: when something *is* it.
PROBES = ("this package is {word}", "this package would receive {word}")

#: Words a document really can be, which no probe may turn into a judgment. If
#: either probe were trivially true, every assertion below would pass over a
#: vocabulary of nonsense.
NOT_JUDGMENTS = ("valid", "readable", "parsed", "structural", "present", "json")


def test_every_word_this_server_refuses_is_one_the_guard_refuses() -> None:
    """The two lists cannot be one import, so a test holds them together.

    ``ai/guard.py`` is the lexical boundary the model-backed commands are held
    to, and this module may not import that package -- the import boundary is
    the property this server exists to keep. So the vocabulary is duplicated
    and pinned: a word that stops being a judgment there fails here, which is
    the direction that matters.
    """
    assert JUDGMENT_VOCABULARY
    for word in sorted(JUDGMENT_VOCABULARY):
        assert any(guard.is_judgment(probe.format(word=word)) for probe in PROBES), word


def test_the_probes_can_tell_a_judgment_from_a_fact() -> None:
    for word in NOT_JUDGMENTS:
        assert not any(guard.is_judgment(probe.format(word=word)) for probe in PROBES), word
        assert word not in JUDGMENT_VOCABULARY


@pytest.mark.parametrize(
    "name", ["is_compliant", "is-the-system-secure", "was_the_package_authorized", "ATO_READY"]
)
def test_a_request_for_a_verdict_is_refused_with_the_boundary(name: str) -> None:
    answered = _call(ROOT, name)
    assert answered["outcome"] == "refused"
    assert BOUNDARY in answered["reason"]
    assert answered["available_tools"] == sorted(HANDLERS)


@pytest.mark.parametrize("name", ["list_documents", "check-security", "run_assessment"])
def test_an_ordinary_unknown_tool_is_refused_without_the_boundary(name: str) -> None:
    """The boundary sentence has to mean something, so it cannot be on everything.

    ``check-security`` and ``run_assessment`` are here on purpose: neither
    ``security`` nor ``assessment`` is a word ``ai/guard.py`` treats as a
    judgment, so neither is one this server claims to detect. Both are still
    refused, and the answer names the four tools that do exist.
    """
    answered = _call(ROOT, name)
    assert answered["outcome"] == "refused"
    assert BOUNDARY not in answered["reason"]
    assert answered["available_tools"] == sorted(HANDLERS)


@pytest.mark.parametrize("name", ["validator", "insecurely", "certifiable", *HANDLERS])
def test_the_vocabulary_is_matched_on_whole_words(name: str) -> None:
    """``ato`` is inside ``validator``; a substring scan would refuse the tool."""
    assert not is_judgment_request(name)


# -- the process -------------------------------------------------------------


def test_no_module_under_the_model_layer_is_loaded_by_the_server_process() -> None:
    """Every tool driven in a fresh interpreter, then the loaded modules read.

    All four, not one: a boundary that holds for the tool a test happens to
    pick says nothing about the other three.
    """
    requests = [
        _request(1, "validate", {"path": "clean_catalog.json"}),
        _request(2, "rule", {"identifier": "REFERENCE_UNVERIFIABLE"}),
        _request(3, "coverage", {}),
        _request(4, "limits", {}),
    ]
    script = (
        "import io, json, sys\n"
        "from pathlib import Path\n"
        "from oscal_validate.mcp import serve\n"
        f"lines = {json.dumps(chr(10).join(requests) + chr(10))}\n"
        "out = io.StringIO()\n"
        f"serve(Path({str(FIXTURES)!r}), io.StringIO(lines), out)\n"
        "answers = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]\n"
        "loaded = sorted(m for m in sys.modules if m.startswith(('oscal_validate.ai', "
        "'anthropic', 'httpx', 'boto')))\n"
        "print(json.dumps({'answered': [a['id'] for a in answers], "
        "'errors': [a.get('error') for a in answers if 'error' in a], 'loaded': loaded}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    assert observed["answered"] == [1, 2, 3, 4]
    assert observed["errors"] == []
    assert observed["loaded"] == []
