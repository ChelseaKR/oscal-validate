"""The survey harness fetches politely, or it does not fetch.

`tools/fetch.py` is the only code in this repository that opens a socket, and
it is not part of the installed package. Its promises are proved here against a
server on localhost, so no test ever reaches the internet.
"""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from fetch import PRODUCT_TOKEN, BlockedError, Fetcher, FetchError, user_agent  # noqa: E402
from survey import _acquire, read_provenance  # noqa: E402


@dataclass
class Route:
    status: int = 200
    body: bytes = b""
    content_type: str = "application/json"
    location: str | None = None


@dataclass
class Site:
    base: str = ""
    requests: list[tuple[str, str]] = field(default_factory=list)


def _handler(routes: dict[str, Route], site: Site) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self) -> None:  # noqa: N802 - the name the stdlib dispatches on
            site.requests.append((self.path, self.headers.get("User-Agent", "")))
            route = routes.get(self.path)
            if route is None:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"not found")
                return
            self.send_response(route.status)
            if route.location is not None:
                self.send_header("Location", route.location)
            self.send_header("Content-Type", route.content_type)
            self.send_header("Content-Length", str(len(route.body)))
            self.end_headers()
            self.wfile.write(route.body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


@contextmanager
def serve(routes: dict[str, Route]) -> Iterator[Site]:
    site = Site()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(routes, site))
    site.base = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield site
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def robots(body: str) -> Route:
    return Route(body=body.encode(), content_type="text/plain")


ALLOW_ALL = robots("User-agent: *\nDisallow:\n")


def _fetcher() -> Fetcher:
    return Fetcher(min_interval=0.0, timeout=5.0)


def test_the_user_agent_names_the_tool_and_links_to_the_repository() -> None:
    agent = user_agent()
    assert PRODUCT_TOKEN in agent
    assert "github.com/ChelseaKR/oscal-validate" in agent


def test_robots_is_read_before_the_document() -> None:
    with serve({"/robots.txt": ALLOW_ALL, "/a.json": Route(body=b"{}")}) as site:
        _fetcher().fetch(f"{site.base}/a.json")
        assert [path for path, _ in site.requests] == ["/robots.txt", "/a.json"]


def test_a_disallow_stops_the_fetch_before_the_document_is_requested() -> None:
    blocked = robots(f"User-agent: {PRODUCT_TOKEN}\nDisallow: /\n")
    with serve({"/robots.txt": blocked, "/a.json": Route(body=b"{}")}) as site:
        with pytest.raises(BlockedError):
            _fetcher().fetch(f"{site.base}/a.json")
        assert [path for path, _ in site.requests] == ["/robots.txt"]


def test_there_is_no_flag_to_override_robots() -> None:
    import inspect

    signature = inspect.signature(Fetcher.__init__)
    names = " ".join(signature.parameters).lower()
    for word in ("ignore", "force", "override", "skip"):
        assert word not in names


def test_a_missing_robots_permits_the_fetch() -> None:
    with serve({"/a.json": Route(body=b"{}")}) as site:
        result = _fetcher().fetch(f"{site.base}/a.json")
        assert "RFC 9309 2.3.1.3" in result.robots


def test_an_unreachable_robots_stops_everything_on_that_host() -> None:
    with serve({"/robots.txt": Route(status=503), "/a.json": Route(body=b"{}")}) as site:
        with pytest.raises(FetchError, match="2.3.1.4"):
            _fetcher().fetch(f"{site.base}/a.json")
        assert [path for path, _ in site.requests] == ["/robots.txt"]


def test_redirects_are_followed_and_capped() -> None:
    routes = {"/robots.txt": ALLOW_ALL, "/final.json": Route(body=b"{}")}
    routes["/start.json"] = Route(status=302, location="/final.json")
    with serve(routes) as site:
        result = _fetcher().fetch(f"{site.base}/start.json")
        assert result.final_url.endswith("/final.json")

    loop = {"/robots.txt": ALLOW_ALL, "/loop.json": Route(status=302, location="/loop.json")}
    with serve(loop) as site, pytest.raises(FetchError, match="redirects"):
        _fetcher().fetch(f"{site.base}/loop.json")


def test_only_http_and_https_are_opened() -> None:
    for url in ("file:///etc/passwd", "data:application/json,{}", "ftp://example.org/a.json"):
        with pytest.raises(FetchError, match="only http and https"):
            _fetcher().fetch(url)


def test_a_document_larger_than_the_cap_is_refused() -> None:
    body = b"x" * 4096
    with serve({"/robots.txt": ALLOW_ALL, "/big.json": Route(body=body)}) as site:
        fetcher = Fetcher(min_interval=0.0, max_bytes=16, timeout=5.0)
        with pytest.raises(FetchError, match="byte cap"):
            fetcher.fetch(f"{site.base}/big.json")


def test_an_http_error_is_loud_rather_than_an_empty_document() -> None:
    with serve({"/robots.txt": ALLOW_ALL}) as site, pytest.raises(FetchError, match="HTTP 404"):
        _fetcher().fetch(f"{site.base}/missing.json")


def test_a_fetch_is_dated_at_the_moment_its_bytes_arrived() -> None:
    """Lineage per record, not per file: the retrieval carries its own UTC date.

    Bracketed by two readings of the clock rather than compared to a fixed
    string, so this measures that the recorded moment is the moment of the
    fetch. A constant would pass just as well against a hardcoded date.
    """
    with serve({"/robots.txt": ALLOW_ALL, "/a.json": Route(body=b"{}")}) as site:
        before = datetime.now(tz=UTC).replace(microsecond=0)
        result = _fetcher().fetch(f"{site.base}/a.json")
        after = datetime.now(tz=UTC)

    assert result.fetched_at.endswith("Z"), result.fetched_at
    recorded = datetime.fromisoformat(result.fetched_at)
    assert recorded.utcoffset() == UTC.utcoffset(None), result.fetched_at
    assert before <= recorded <= after
    assert result.to_dict()["fetched_at"] == result.fetched_at


def test_the_survey_record_is_dated_by_the_run_that_reached_the_network(tmp_path: Path) -> None:
    """The date belongs to the retrieval, and a later run does not restamp it.

    A second run reads the cache and records no fetch of its own, so it has no
    date to give: without provenance the record carries no ``fetch`` block at
    all, which is the absence stated rather than the cache's own mtime dressed
    up as a retrieval. ``--provenance`` then hands it the first run's block,
    ``fetched_at`` included, so the date that reaches the evidence is the one
    the bytes actually have.
    """
    cache = tmp_path / "cache"
    with serve({"/robots.txt": ALLOW_ALL, "/a.json": Route(body=b"{}")}) as site:
        url = f"{site.base}/a.json"
        _, fetched = _acquire(_fetcher(), cache, url, offline=False, provenance={})
        _, cached = _acquire(_fetcher(), cache, url, offline=False, provenance={})

    assert fetched["outcome"] == "fetched"
    assert fetched["fetch"]["fetched_at"]
    assert cached == {"outcome": "read from cache"}

    earlier_run = tmp_path / "earlier-run.json"
    earlier_run.write_text(
        json.dumps({"records": [{"url": url, **fetched}], "supporting": []}), encoding="utf-8"
    )
    carried = read_provenance([earlier_run])
    _, again = _acquire(_fetcher(), cache, url, offline=True, provenance=carried)
    assert again["fetch"] == fetched["fetch"]
