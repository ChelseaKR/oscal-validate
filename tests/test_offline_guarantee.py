"""The no-network promise, enforced rather than asserted.

The README says this tool opens no network connection in any code path. That
is a claim worth proving instead of repeating, so these tests take the socket
away and run the whole validator anyway.
"""

from __future__ import annotations

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
def test_an_unresolved_import_is_never_a_fetch(capsys: pytest.CaptureFixture[str]) -> None:
    # The profile names a catalog it was not given. A tool that fetched would
    # fetch here; this one reports UNVERIFIABLE instead.
    assert main([str(fixture_path("clean_profile.json"))]) == 0
    out = capsys.readouterr().out
    assert "IMPORT_NOT_SUPPLIED" in out
    assert "UNVERIFIABLE" in out


def test_the_installed_package_imports_no_network_module() -> None:
    # The fetcher lives in tools/, outside the package, precisely so that this
    # holds. If it ever moves inside, this fails.
    source_root = Path(__file__).resolve().parent.parent / "src" / "oscal_validate"
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for module in ("urllib.request", "http.client", "socket", "requests", "httpx"):
            assert f"import {module}" not in text, f"{path.name} imports {module}"
