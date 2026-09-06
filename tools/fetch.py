"""The only code in this repository that opens a network connection.

It is not part of the installed package. ``oscal-validate`` itself has no
network capability in any command; this module lives under ``tools/`` and is
used only to collect the published documents behind ``docs/findings/``.

The posture, in full:

- **robots.txt is fetched first and obeyed.** A Disallow for this tool's
  product token is a hard stop. There is no override flag, because a flag to
  ignore robots.txt is the whole of the harm. A host that disallows is recorded
  as blocked and skipped, never worked around.
- **An unreachable robots.txt is a stop, not a shrug** (RFC 9309 section
  2.3.1.4). A 4xx means no robots.txt exists and the fetch may proceed
  (section 2.3.1.3).
- **The User-Agent identifies the tool and links to its source** (section
  2.2.1), with the product token as a substring.
- **Redirects are followed manually, at most five**, with robots.txt re-checked
  at every hop, so a redirect cannot carry the fetch onto a host that said no.
- **Rate limited per host**, with a minimum interval a site's own
  ``Crawl-delay`` can lengthen but never shorten.
- **Every retrieval is dated.** A :class:`FetchResult` records the UTC moment
  its bytes arrived, so a survey's evidence is dated per record rather than
  only by the name of the file it was written to.
- **Failures are loud.** Every stop raises :class:`FetchError`.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

#: RFC 9309 section 2.2.1: a product token is letters, underscores, and hyphens.
PRODUCT_TOKEN = "oscal-validate"  # noqa: S105 - a robots.txt product token, not a secret
SOURCE_URL = "https://github.com/ChelseaKR/oscal-validate"
VERSION = "0.1.0"

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_BYTES = 24 * 1024 * 1024
DEFAULT_MIN_INTERVAL = 2.0
#: RFC 9309 section 2.3.1.2: follow at least five consecutive redirects.
MAX_REDIRECTS = 5
#: RFC 9309 section 2.5: "The parsing limit MUST be at least 500 kibibytes."
ROBOTS_MAX_BYTES = 512 * 1024

ALLOWED_SCHEMES = ("http", "https")
REDIRECT_STATUSES = (301, 302, 303, 307, 308)

Headers = dict[str, str]


def user_agent(contact: str | None = None) -> str:
    detail = f"+{SOURCE_URL}" + (f"; {contact}" if contact else "")
    return f"{PRODUCT_TOKEN}/{VERSION} ({detail})"


def retrieved_at() -> str:
    """The moment of retrieval: UTC, RFC 3339, whole seconds.

    Always UTC and always the ``Z`` form, because the evidence this ends up in
    is read by people in other timezones than whoever ran the survey, and a
    local offset would make two runs' dates look different when they are not.

    Whole seconds rather than microseconds: this is taken once the response
    body has finished arriving, so it dates the retrieval and not the request,
    and sub-second digits would claim a precision it does not have.
    """
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class FetchError(RuntimeError):
    """The document could not be fetched, for any reason, including robots.txt."""


class BlockedError(FetchError):
    """robots.txt disallows this tool. Recorded and skipped, never circumvented."""


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    status: int
    content_type: str
    bytes_read: int
    redirects: tuple[str, ...]
    robots: str
    fetched_at: str
    body: bytes

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "status": self.status,
            "content_type": self.content_type,
            "bytes": self.bytes_read,
            "redirects": list(self.redirects),
            "robots": self.robots,
            "fetched_at": self.fetched_at,
        }


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Hand redirects back to the caller so robots.txt can be re-checked."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def origin_of(url: str) -> str:
    parts = urlparse(url)
    return urlunparse((parts.scheme, parts.netloc, "", "", "", ""))


def _headers(raw: object) -> Headers:
    items = raw.items() if hasattr(raw, "items") else []
    return {str(name).lower(): str(value) for name, value in items}


class Fetcher:
    """A polite HTTP client. One per run; it holds the rate limit."""

    def __init__(
        self,
        contact: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_BYTES,
        min_interval: float = DEFAULT_MIN_INTERVAL,
    ) -> None:
        self.user_agent = user_agent(contact)
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.min_interval = min_interval
        self._opener = urllib.request.build_opener(_NoRedirects)
        self._robots: dict[str, tuple[RobotFileParser | None, str]] = {}
        self._delays: dict[str, float] = {}
        self._last_request: dict[str, float] = {}

    # -- transport --------------------------------------------------------

    def _request(self, url: str, limit: int) -> tuple[int, Headers, bytes]:
        # The URL comes from the operator's own target list and is restricted
        # to http and https by _require_fetchable before this is reached. No
        # response body is executed or interpreted here.
        request = urllib.request.Request(  # noqa: S310 - scheme checked above
            url,
            headers={"User-Agent": self.user_agent, "Accept": "application/json, */*"},
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return int(response.status), _headers(response.headers), response.read(limit + 1)
        except urllib.error.HTTPError as exc:
            body = exc.read(limit + 1)
            headers = _headers(exc.headers)
            exc.close()
            return int(exc.code), headers, body
        except (urllib.error.URLError, OSError) as exc:
            raise FetchError(f"{url}: request failed ({exc})") from exc

    def _wait(self, origin: str) -> None:
        delay = self._delays.get(origin, self.min_interval)
        previous = self._last_request.get(origin)
        if previous is not None:
            remaining = delay - (time.monotonic() - previous)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request[origin] = time.monotonic()

    # -- robots.txt -------------------------------------------------------

    def _robots_for(self, origin: str) -> tuple[RobotFileParser | None, str]:
        cached = self._robots.get(origin)
        if cached is not None:
            return cached
        self._wait(origin)
        result = self._read_robots(f"{origin}/robots.txt")
        self._robots[origin] = result
        return result

    def _read_robots(self, robots_url: str) -> tuple[RobotFileParser | None, str]:
        current = robots_url
        for _ in range(MAX_REDIRECTS + 1):
            status, headers, body = self._request(current, ROBOTS_MAX_BYTES)
            location = headers.get("location")
            if status in REDIRECT_STATUSES and location:
                current = urljoin(current, location)
                continue
            return self._robots_from_response(status, body, current)
        raise FetchError(f"{robots_url}: more than {MAX_REDIRECTS} redirects fetching robots.txt")

    def _robots_from_response(
        self, status: int, body: bytes, url: str
    ) -> tuple[RobotFileParser | None, str]:
        if 200 <= status < 300:
            parser = RobotFileParser()
            parser.parse(body[:ROBOTS_MAX_BYTES].decode("utf-8", errors="replace").splitlines())
            return parser, f"read from {url} (HTTP {status})"
        if 400 <= status < 500:
            # RFC 9309 2.3.1.3: unavailable, so any resource may be accessed.
            return None, f"none published at {url} (HTTP {status}); RFC 9309 2.3.1.3 allows it"
        # RFC 9309 2.3.1.4: unreachable means complete disallow.
        raise FetchError(
            f"{url}: HTTP {status}. RFC 9309 section 2.3.1.4 requires a crawler to assume "
            "complete disallow when robots.txt is unreachable, so nothing was fetched from "
            "this host."
        )

    def _check_robots(self, url: str) -> str:
        origin = origin_of(url)
        parser, description = self._robots_for(origin)
        if parser is None:
            return description
        if not parser.can_fetch(self.user_agent, url):
            raise BlockedError(
                f"{url}: disallowed by {origin}/robots.txt for the product token "
                f"{PRODUCT_TOKEN}. Recorded and skipped; there is no flag to override it."
            )
        delay = parser.crawl_delay(self.user_agent)
        if delay is not None:
            self._delays[origin] = max(self.min_interval, float(delay))
        return f"{description}, fetch allowed"

    # -- the fetch --------------------------------------------------------

    def fetch(self, url: str) -> FetchResult:
        """Fetch one document politely, or raise FetchError saying exactly why not."""
        current = url
        redirects: list[str] = []
        for _ in range(MAX_REDIRECTS + 1):
            _require_fetchable(current)
            robots = self._check_robots(current)
            self._wait(origin_of(current))
            status, headers, body = self._request(current, self.max_bytes)
            location = headers.get("location")
            if status in REDIRECT_STATUSES and location:
                current = urljoin(current, location)
                redirects.append(current)
                continue
            if not 200 <= status < 300:
                raise FetchError(f"{current}: HTTP {status}")
            if len(body) > self.max_bytes:
                raise FetchError(f"{current}: response exceeds the {self.max_bytes} byte cap")
            return FetchResult(
                requested_url=url,
                final_url=current,
                status=status,
                content_type=headers.get("content-type", ""),
                bytes_read=len(body),
                redirects=tuple(redirects),
                robots=robots,
                fetched_at=retrieved_at(),
                body=body,
            )
        raise FetchError(
            f"{url}: more than {MAX_REDIRECTS} redirects. RFC 9309 section 2.3.1.2 sets "
            "five as the limit a crawler must follow; beyond it this tool stops."
        )


def _require_fetchable(url: str) -> None:
    parts = urlparse(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise FetchError(
            f"{url}: only http and https URLs are fetched (got "
            f"{parts.scheme or 'no scheme'}). Nothing else is opened, including file: "
            "and data: URLs."
        )
    if not parts.netloc:
        raise FetchError(f"{url}: no host in the URL")
