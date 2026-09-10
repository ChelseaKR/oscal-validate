"""The no-network promise, enforced rather than asserted.

The README says the validation commands open no network connection in any
code path. That is a claim worth proving instead of repeating, so these tests
take the socket away and run the whole validator anyway.

ADR-0005 added one package that does call out: ``oscal_validate.ai``, the
opt-in model-backed commands. The scan below therefore has three parts
instead of one. Nothing outside ``ai/`` may import a network module; nothing
outside ``ai/`` may import ``ai/``; and ``ai/`` itself may name the SDK only
inside a function, never at module level, so that importing it is free and
the default command never loads it (``tests/test_default_path_byte_identity``
proves that last part in a fresh process).
"""

from __future__ import annotations

import io
import json
import socket
from pathlib import Path
from typing import Any, NoReturn

import pytest

from oscal_validate.cli import main

from .conftest import fixture_path


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError("this code path must not open a socket")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.mark.usefixtures("no_network")
def test_validation_opens_no_socket(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(fixture_path("clean_catalog.json"))]) == 0
    assert "finding(s)" in capsys.readouterr().out


@pytest.mark.usefixtures("no_network")
def test_the_rule_verb_opens_no_socket(capsys: pytest.CaptureFixture[str]) -> None:
    """``rule`` quotes NIST's pages and never fetches one.

    Everything it prints is already on disk, hash-pinned, with the date it was
    retrieved recorded beside it. A verb that reached for a URL when a section
    were missing would be the opposite of what it exists to prove.
    """
    assert main(["rule", "oscal-catalog-controls"]) == 0
    out = capsys.readouterr().out
    assert "sha256: " in out
    assert "https://pages.nist.gov/" in out


@pytest.mark.usefixtures("no_network")
def test_the_mcp_server_answers_every_tool_with_no_socket() -> None:
    """The server's whole claim is read-only and offline; this is the offline half.

    All four tools, driven through the real request loop, because a boundary
    proved on the one tool a test happened to pick says nothing about the
    other three -- and the tool most likely to reach for the network is
    ``validate``, which is handed a profile naming a catalog it was not
    given. A server that fetched would fetch there.
    """
    from oscal_validate.mcp import HANDLERS, serve

    requests = [
        {"name": "validate", "arguments": {"path": "clean_profile.json"}},
        {"name": "rule", "arguments": {"identifier": "REFERENCE_UNVERIFIABLE"}},
        {"name": "coverage", "arguments": {}},
        {"name": "limits", "arguments": {}},
    ]
    assert {call["name"] for call in requests} == set(HANDLERS), "a tool goes unexercised here"
    lines = "\n".join(
        json.dumps({"jsonrpc": "2.0", "id": n, "method": "tools/call", "params": params})
        for n, params in enumerate(requests, start=1)
    )
    sink = io.StringIO()
    assert serve(fixture_path("clean_profile.json").parent, io.StringIO(lines + "\n"), sink) == 0
    answers = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert [answer["id"] for answer in answers] == [1, 2, 3, 4]
    assert all("result" in answer for answer in answers), answers
    served = json.loads(answers[0]["result"]["content"][0]["text"])
    assert "IMPORT_NOT_SUPPLIED" in {f["code"] for f in served["report"]["findings"]}


def test_the_offline_source_scan_reaches_the_mcp_server() -> None:
    """The scan below is what proves the server imports nothing that dials out.

    A file-set the scan does not contain is a claim nothing checks, and this
    module is the newest thing inside it.
    """
    assert SOURCE_ROOT / "mcp.py" in _validator_sources()


@pytest.mark.usefixtures("no_network")
def test_an_unresolved_import_is_never_a_fetch(capsys: pytest.CaptureFixture[str]) -> None:
    # The profile names a catalog it was not given. A tool that fetched would
    # fetch here; this one reports UNVERIFIABLE instead.
    assert main([str(fixture_path("clean_profile.json"))]) == 0
    out = capsys.readouterr().out
    assert "IMPORT_NOT_SUPPLIED" in out
    assert "UNVERIFIABLE" in out


SOURCE_ROOT = Path(__file__).resolve().parent.parent / "src" / "oscal_validate"
AI_ROOT = SOURCE_ROOT / "ai"
NETWORK_MODULES = ("urllib.request", "http.client", "socket", "requests", "httpx", "anthropic")


def _validator_sources() -> list[Path]:
    return sorted(p for p in SOURCE_ROOT.rglob("*.py") if AI_ROOT not in p.parents)


def test_the_validator_imports_no_network_module() -> None:
    # The fetcher lives in tools/, outside the package, precisely so that this
    # holds. If it ever moves inside, this fails.
    assert _validator_sources(), "no validator sources found"
    for path in _validator_sources():
        text = path.read_text(encoding="utf-8")
        for module in NETWORK_MODULES:
            assert f"import {module}" not in text, f"{path.name} imports {module}"
            assert f"from {module}" not in text, f"{path.name} imports from {module}"


def test_nothing_outside_the_ai_package_imports_it() -> None:
    for path in _validator_sources():
        text = path.read_text(encoding="utf-8")
        assert "from .ai" not in text and "from . import ai" not in text, path.name
        assert "oscal_validate.ai" not in text or path.name == "cli.py", path.name
    # cli.py may name the package in a string for the lazy dispatch, and only
    # there; it may not import it at module level.
    cli = (SOURCE_ROOT / "cli.py").read_text(encoding="utf-8")
    for line in cli.splitlines():
        stripped = line.strip()
        forbidden = ("from .ai", "from oscal_validate.ai", "import oscal_validate.ai")
        assert not stripped.startswith(forbidden), line


def test_the_ai_package_imports_the_sdk_only_inside_functions() -> None:
    assert AI_ROOT.is_dir()
    for path in sorted(AI_ROOT.rglob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(("import anthropic", "from anthropic")):
                raise AssertionError(f"{path.name} imports the SDK at module level: {line}")
