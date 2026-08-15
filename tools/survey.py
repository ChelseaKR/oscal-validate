"""Fetch published OSCAL documents, validate them, and record what came back.

This is the harness behind ``docs/findings/``. It is deliberately thin: it
fetches each document through the polite ``Fetcher`` in ``tools/fetch.py``,
runs the same validator the CLI runs, and writes down the outcome.

What it records is metadata and findings only: the HTTP outcome, the model, the
byte size, the finding codes and their counts, and one example location per
code. It never records a document's content. The question is whether published
OSCAL conforms to the published spec, not what anyone's control baseline says,
and a findings file full of other people's system descriptions would be both
unnecessary and rude.

    uv run python tools/survey.py tools/survey-urls.txt out.json --cache .cache

``--cache`` keeps the fetched bytes on disk so a re-run needs no network, and
so that imports can be resolved against documents fetched earlier in the run.
Each document is cached under a directory named for a hash of its URL, keeping
its own file name, so two publishers' ``catalog.json`` cannot collide and the
validator can still match an import by file name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch import BlockedError, Fetcher, FetchError  # noqa: E402

from oscal_validate.document import DocumentError  # noqa: E402
from oscal_validate.findings import counts  # noqa: E402
from oscal_validate.schema import SchemaError  # noqa: E402
from oscal_validate.validator import build_session, validate  # noqa: E402


def read_targets(path: Path) -> list[tuple[str, str, list[str]]]:
    """Lines of ``group<TAB>url[<TAB>resolve-url,resolve-url]``."""
    targets: list[tuple[str, str, list[str]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("\t")
        group, url = parts[0].strip(), parts[1].strip()
        resolve = [p.strip() for p in parts[2].split(",")] if len(parts) > 2 else []
        targets.append((group, url, resolve))
    urls = [url for _, url, _ in targets]
    duplicates = {url for url in urls if urls.count(url) > 1}
    if duplicates:
        raise SystemExit(f"duplicate target URLs: {sorted(duplicates)}")
    return targets


def cache_path(cache: Path, url: str) -> Path:
    """Where a URL's bytes live: a per-URL directory, the publisher's own name.

    The directory keeps two publishers' ``catalog.json`` apart; the file name
    inside it is unchanged, because that is what an import href names.
    """
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return cache / digest / (url.rsplit("/", 1)[-1] or "index.json")


def _validate(path: Path, resolve: list[Path]) -> dict[str, Any]:
    session = build_session(path, resolve)
    findings = validate(session)
    by_code: Counter[str] = Counter(finding.code for finding in findings)
    example: dict[str, str] = {}
    for finding in findings:
        example.setdefault(finding.code, finding.location)
    return {
        "model": session.corpus.primary.walked.model,
        "imports": len(session.corpus.edges),
        "imports_resolved": sum(1 for edge in session.corpus.edges if edge.resolved),
        "effective_model_complete": session.corpus.complete,
        "summary": counts(findings),
        "codes": dict(sorted(by_code.items())),
        "example_location": dict(sorted(example.items())),
    }


def run(
    targets: list[tuple[str, str, list[str]]], cache: Path, offline: bool
) -> Iterator[dict[str, Any]]:
    fetcher = Fetcher()
    cache.mkdir(parents=True, exist_ok=True)
    for group, url, resolve in targets:
        record: dict[str, Any] = {"group": group, "url": url}
        path = cache_path(cache, url)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if offline or path.exists():
                record["outcome"] = "read from cache"
            else:
                result = fetcher.fetch(url)
                path.write_bytes(result.body)
                record["outcome"] = "fetched"
                record["fetch"] = result.to_dict()
            record["bytes"] = path.stat().st_size
            record.update(_validate(path, [cache_path(cache, other) for other in resolve]))
        except BlockedError as exc:
            record["outcome"] = "blocked by robots.txt"
            record["reason"] = str(exc)
        except (FetchError, DocumentError, SchemaError, OSError, RecursionError) as exc:
            record["outcome"] = "not read"
            record["reason"] = f"{type(exc).__name__}: {exc}"
        print(f"{record['outcome']:20} {url}", file=sys.stderr)
        yield record


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    read = [r for r in records if "summary" in r]
    codes: Counter[str] = Counter()
    models: Counter[str] = Counter()
    for record in read:
        codes.update(record["codes"])
        models[record["model"]] += 1
    return {
        "targets": len(records),
        "validated": len(read),
        "not_read": len(records) - len(read),
        "blocked": sum(1 for r in records if r["outcome"] == "blocked by robots.txt"),
        "with_errors": sum(1 for r in read if r["summary"]["ERROR"]),
        "with_complete_effective_model": sum(1 for r in read if r["effective_model_complete"]),
        "models": dict(sorted(models.items())),
        "codes": dict(codes.most_common()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", type=Path, help="group<TAB>url per line")
    parser.add_argument("output", type=Path, help="where to write the survey JSON")
    parser.add_argument("--cache", type=Path, default=Path(".survey-cache"))
    parser.add_argument("--offline", action="store_true", help="use the cache only")
    args = parser.parse_args()

    records = list(run(read_targets(args.targets), args.cache, args.offline))
    payload = {"summary": summarize(records), "records": records}
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
