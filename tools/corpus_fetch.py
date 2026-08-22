"""Collect the NIST text corpus the model-backed commands quote from.

    uv run python tools/corpus_fetch.py tools/corpus-urls.txt src/oscal_validate/ai/corpus

Every line of the URL list is ``<id> <url>``. Each page is fetched through
``tools/fetch.py`` (robots.txt first, identifying User-Agent, byte cap,
rate limit), its text is extracted by the standard library's HTML parser in a
fixed, documented way, and the text is written to ``<id>.txt``. A
``MANIFEST.json`` records, per source, the URL, the final URL after
redirects, the page title, the retrieval date, the SHA-256 of the raw bytes
as served, and the SHA-256 and size of the extracted text. The committed text
is what the verifier checks quotes against; the raw hash is how a reader can
tell whether the page has changed since.

The pages are NIST's, public domain in the United States and CC0 elsewhere,
as the OSCAL repository states. Nothing here is edited by hand; a change to
the extraction is a change to this file and a re-run, and
``tests/test_ai_corpus.py`` fails if a text file and its manifest row
disagree.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch import Fetcher, FetchError  # noqa: E402

#: Bumped when the extraction below changes, so a manifest says which one made it.
EXTRACTION_VERSION = "1"

_SKIP = frozenset({"script", "style", "noscript", "nav", "header", "footer", "svg", "button"})
_BLOCK = frozenset(
    {
        "p",
        "div",
        "li",
        "tr",
        "pre",
        "section",
        "article",
        "details",
        "summary",
        "blockquote",
        "table",
        "ul",
        "ol",
        "dl",
        "dt",
        "dd",
        "br",
        "hr",
        "figure",
        "figcaption",
    }
)
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class _Text(HTMLParser):
    """Body text with headings marked and block boundaries kept as line breaks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip_depth = 0
        self._in_title = False
        self._heading: int | None = None
        self._in_pre = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        elif tag in _HEADINGS:
            self._heading = _HEADINGS[tag]
            self.parts.append("\n\n" + "#" * self._heading + " ")
        elif tag == "pre":
            self._in_pre += 1
            self.parts.append("\n")
        elif tag in _BLOCK:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        elif tag in _HEADINGS:
            self._heading = None
            self.parts.append("\n")
        elif tag == "pre":
            self._in_pre = max(0, self._in_pre - 1)
            self.parts.append("\n")
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
            return
        self.parts.append(data if self._in_pre else re.sub(r"\s+", " ", data))


def extract_text(html: str) -> tuple[str, str]:
    parser = _Text()
    parser.feed(html)
    parser.close()
    text = "".join(parser.parts)
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?m)^ +", "", text)
    return text.strip() + "\n", re.sub(r"\s+", " ", parser.title).strip()


def _read_targets(path: Path) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        identifier, url = line.split(None, 1)
        targets.append((identifier, url.strip()))
    return targets


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    targets = _read_targets(Path(argv[0]))
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "MANIFEST.json"
    manifest: dict[str, object] = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    )
    sources = manifest.get("sources")
    if not isinstance(sources, dict):
        sources = {}
    fetcher = Fetcher(contact="ckellyreif@gmail.com", max_bytes=20_000_000)
    today = dt.date.today().isoformat()
    for identifier, url in targets:
        try:
            result = fetcher.fetch(url)
        except FetchError as exc:
            print(f"FAILED {identifier}: {exc}", file=sys.stderr)
            return 1
        html = result.body.decode("utf-8", errors="replace")
        text, title = extract_text(html)
        (out / f"{identifier}.txt").write_text(text, encoding="utf-8")
        sources[identifier] = {
            "url": url,
            "final_url": result.final_url,
            "title": title,
            "retrieved": today,
            "raw_sha256": hashlib.sha256(result.body).hexdigest(),
            "raw_bytes": len(result.body),
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text_bytes": len(text.encode("utf-8")),
        }
        print(f"{identifier}: {len(result.body)} bytes -> {len(text)} chars of text")
    manifest = {
        "extraction_version": EXTRACTION_VERSION,
        "license": (
            "Works of the US National Institute of Standards and Technology; public domain "
            "in the United States, CC0 1.0 elsewhere per usnistgov/OSCAL."
        ),
        "sources": dict(sorted(sources.items())),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
