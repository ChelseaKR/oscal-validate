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

A target line's third column lists the documents to hand it with ``--resolve``.
Those are fetched on the same terms as a target and are *not* themselves
surveyed: a document named only there is a supporting document, part of some
target's effective data model, and it is never counted as a document the survey
reports on. A resolve URL that cannot be fetched stops the run rather than
quietly turning its target into an unreadable one, because a survey that
silently dropped a target would misreport its own denominator.

``--provenance`` carries the ``fetch`` block a previous run recorded for a URL
into this run's record for it. A fetch happens once and the cache answers ever
after, so without it a document retrieved by an earlier run reports only ``read
from cache``: the HTTP status, the final URL, the redirect chain and what
``robots.txt`` said all live in whichever run first reached the network, one
indirection away from the run that used the bytes. The flag takes the committed
findings JSON that recorded those fetches, so every record can carry its own
retrieval evidence.
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
from oscal_validate.findings import Finding, counts  # noqa: E402
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


def _by_url(location: str, source_of: dict[str, str]) -> str:
    """A pointer into a supporting document, named by its URL, not its cache path.

    The validator qualifies a pointer with the path of the file it came from,
    which is right at a terminal and wrong in committed evidence: a cache
    directory is a fact about one laptop. Rewriting it to the URL keeps the
    evidence reproducible on any machine and leaves the reader with something
    they can actually open.
    """
    head, separator, tail = location.partition("#")
    if not separator:
        return location
    return f"{source_of.get(head, head)}{separator}{tail}"


def _example_key(finding: Finding, source_of: dict[str, str]) -> tuple[str, ...]:
    """The validator's own ordering, applied to the *rewritten* location.

    ``Finding.sort_key`` leads with ``location``, and for a finding in a
    supporting document that location is a cache path. So the validator's
    deterministic order is deterministic per machine and not across machines,
    and the first finding of a given code -- the one recorded below as that
    code's example -- moved when the cache moved. Measured on the 2026-08-15
    sample: 7 of 52 records changed with the cache path, and the committed
    evidence differed from a re-run in 9. Counts never varied. One bookkeeping
    field is still enough to stop a committed artifact reproducing.

    Rewriting to the URL before sorting rather than after settles it. The key is
    otherwise the validator's, so the tie-breaks are unchanged: this reorders
    only the axis that was a fact about a laptop.
    """
    location, prop, code, value, severity, message = finding.sort_key()
    return (_by_url(location, source_of), prop, code, value, severity, message)


def _validate(path: Path, resolve: list[Path], source_of: dict[str, str]) -> dict[str, Any]:
    session = build_session(path, resolve)
    findings = validate(session)
    by_code: Counter[str] = Counter(finding.code for finding in findings)
    example: dict[str, str] = {}
    for finding in sorted(findings, key=lambda f: _example_key(f, source_of)):
        example.setdefault(finding.code, _by_url(finding.location, source_of))
    return {
        "model": session.corpus.primary.walked.model,
        "imports": len(session.corpus.edges),
        "imports_resolved": sum(1 for edge in session.corpus.edges if edge.resolved),
        "effective_model_complete": session.corpus.complete,
        "summary": counts(findings),
        "codes": dict(sorted(by_code.items())),
        "example_location": dict(sorted(example.items())),
    }


def read_provenance(paths: list[Path]) -> dict[str, dict[str, Any]]:
    """URL -> the ``fetch`` block some earlier run recorded for it.

    Read from previous findings JSON, which is where a fetch that has already
    happened is written down. Targets and supporting documents both carry one,
    and a URL that is a target in one run and a supporting document in another
    is the same retrieval either way.
    """
    recorded: dict[str, dict[str, Any]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for entry in list(payload.get("records", [])) + list(payload.get("supporting", [])):
            fetch = entry.get("fetch")
            if fetch is not None:
                recorded.setdefault(entry["url"], fetch)
    return recorded


def _acquire(
    fetcher: Fetcher,
    cache: Path,
    url: str,
    offline: bool,
    provenance: dict[str, dict[str, Any]],
) -> tuple[Path, dict[str, Any]]:
    """The cached bytes for one URL, fetched if they are not there yet."""
    path = cache_path(cache, url)
    path.parent.mkdir(parents=True, exist_ok=True)
    if offline or path.exists():
        recorded = provenance.get(url)
        cached: dict[str, Any] = {"outcome": "read from cache"}
        if recorded is not None:
            cached["fetch"] = recorded
        return path, cached
    result = fetcher.fetch(url)
    path.write_bytes(result.body)
    return path, {"outcome": "fetched", "fetch": result.to_dict()}


def supporting(
    targets: list[tuple[str, str, list[str]]],
    cache: Path,
    offline: bool,
    fetcher: Fetcher,
    provenance: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Acquire every document any target names in its ``--resolve`` column.

    Done in one pass before anything is validated, so that each supporting
    document's own provenance is recorded once rather than attributed to
    whichever target happened to reach it first. These documents are not
    surveyed: they are somebody's effective data model, not a document the
    survey reports on, and they are never counted in the denominator.

    A failure here is raised rather than recorded. A run that quietly reported
    a target as unreadable because a supporting document was missing would be
    reporting the wrong thing about the wrong file.
    """
    seen: list[dict[str, Any]] = []
    done: set[str] = set()
    for _, _, resolve in targets:
        for url in resolve:
            if url in done:
                continue
            done.add(url)
            path, outcome = _acquire(fetcher, cache, url, offline, provenance or {})
            if not path.exists():
                raise FetchError(f"{url}: named with --resolve and not in the cache")
            print(f"  {outcome['outcome']:18} {url}  (--resolve)", file=sys.stderr)
            seen.append({"url": url, "bytes": path.stat().st_size, **outcome})
    return seen


def run(
    targets: list[tuple[str, str, list[str]]],
    cache: Path,
    offline: bool,
    fetcher: Fetcher,
    provenance: dict[str, dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    for group, url, resolve in targets:
        record: dict[str, Any] = {"group": group, "url": url, "resolve": list(resolve)}
        try:
            path, outcome = _acquire(fetcher, cache, url, offline, provenance or {})
            record.update(outcome)
            record["bytes"] = path.stat().st_size
            supporting = {str(cache_path(cache, other)): other for other in resolve}
            record.update(_validate(path, [Path(p) for p in supporting], supporting))
        except BlockedError as exc:
            record["outcome"] = "blocked by robots.txt"
            record["reason"] = str(exc)
        except (FetchError, DocumentError, SchemaError, OSError, RecursionError) as exc:
            record["outcome"] = "not read"
            record["reason"] = f"{type(exc).__name__}: {exc}"
        print(f"{record['outcome']:20} {url}", file=sys.stderr)
        yield record


def summarize(records: list[dict[str, Any]], supplied: list[dict[str, Any]]) -> dict[str, Any]:
    read = [r for r in records if "summary" in r]
    codes: Counter[str] = Counter()
    models: Counter[str] = Counter()
    for record in read:
        codes.update(record["codes"])
        models[record["model"]] += 1
    supporting = {entry["url"] for entry in supplied}
    return {
        "targets": len(records),
        "validated": len(read),
        "not_read": len(records) - len(read),
        "blocked": sum(1 for r in records if r["outcome"] == "blocked by robots.txt"),
        "with_errors": sum(1 for r in read if r["summary"]["ERROR"]),
        "with_complete_effective_model": sum(1 for r in read if r["effective_model_complete"]),
        "supporting_documents": len(supporting),
        "supporting_not_also_targets": len(supporting - {r["url"] for r in records}),
        "import_edges": sum(r.get("imports", 0) for r in read),
        "import_edges_resolved": sum(r.get("imports_resolved", 0) for r in read),
        "models": dict(sorted(models.items())),
        "codes": dict(codes.most_common()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", type=Path, help="group<TAB>url per line")
    parser.add_argument("output", type=Path, help="where to write the survey JSON")
    parser.add_argument("--cache", type=Path, default=Path(".survey-cache"))
    parser.add_argument("--offline", action="store_true", help="use the cache only")
    parser.add_argument(
        "--provenance",
        type=Path,
        action="append",
        default=[],
        metavar="FINDINGS.json",
        help="carry forward the fetch records an earlier run wrote for these URLs",
    )
    args = parser.parse_args()

    targets = read_targets(args.targets)
    provenance = read_provenance(args.provenance)
    args.cache.mkdir(parents=True, exist_ok=True)
    fetcher = Fetcher()
    supplied = supporting(targets, args.cache, args.offline, fetcher, provenance)
    records = list(run(targets, args.cache, args.offline, fetcher, provenance))
    payload = {
        "summary": summarize(records, supplied),
        "supporting": supplied,
        "records": records,
    }
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
