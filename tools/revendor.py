"""Re-vendor NIST's OSCAL release -- and say what it would change before anything is written.

Every check in this tool reads the vendored files, so a new OSCAL release is not
a version bump; it is a change to what the tool can say. This harness makes the
cost of that change visible before it is paid::

    uv run python tools/revendor.py 1.2.4            # fetch, diff, write nothing
    uv run python tools/revendor.py --from-dir DIR   # a candidate already on disk
    uv run python tools/revendor.py 1.2.4 --write    # write, after the diff is printed

It is a development harness like ``tools/fetch.py``, not part of the package,
and it never runs in CI.

**Writing is opt-in and comes last.** The default run writes nothing. With
``--write`` the diff is still computed and printed first; a re-vendor that
wrote before it reported could not be reviewed.

**Computed by the same parser, literally.** The package is copied to a
temporary directory with the candidate's bytes swapped into ``vendor/oscal/``,
and that copy's own ``load_metaschema()`` and ``load_schema()`` produce the
candidate inventory in a subprocess -- the same code that produces the current
one, reading different bytes. Parsing the candidate in-process would not be
the same thing: the loaders are cached, and ``metaschema_datatype`` reaches
``load_schema()`` directly, so the two releases would quietly mix. The
subprocess asserts that it imported the copy before it answers, so an
inventory cannot silently be the installed package describing itself.

**Golden impact runs the goldens through the copy.** The case list and the
runner are ``tests/golden/capture.py``'s own, and which findings appear or
disappear is ``oscal_validate.compare``'s, so this file holds no second copy of
either. It also prints how many golden findings come from an *evaluated*
constraint at all, because "no golden moved" means nothing without that
denominator -- and on OSCAL 1.2.3 it is zero: the goldens pin the default
path over clean documents, and a change to an evaluated constraint's level
reaches none of them.

**Refusals, all exit 2:** a candidate file carrying ``<!DOCTYPE`` or
``<!ENTITY`` (checked before anything else reads it), a missing file, a fetch
robots.txt disallows or that fails, and a candidate this tool's reader cannot
parse. Otherwise the exit code is 0 when nothing would change and 1 when
something would, like ``diff``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from oscal_validate.compare import compare, findings_from_report  # noqa: E402
from oscal_validate.metaschema import FORBIDDEN_MARKUP, load_metaschema  # noqa: E402
from oscal_validate.snapshot import VENDORED_FILES  # noqa: E402
from tests.golden.capture import CACHE, CACHED, CASES, GOLDEN, run  # noqa: E402

PACKAGE = ROOT / "src" / "oscal_validate"
VENDOR = PACKAGE / "vendor"
SOURCES = VENDOR / "SOURCES.md"

#: Where NIST publishes each release's artifacts.
RELEASE_URL = "https://github.com/usnistgov/OSCAL/releases/download/v{version}/{name}"

#: The one vendored file renamed on the way in; see ``vendor/SOURCES.md``.
RENAMED = {"complete_schema.json": "oscal_complete_schema.json"}

#: The finding every report carries for the constraints this tool does not
#: evaluate. It counts them across the whole release, not per model
#: (``checks/constraints.py:_coverage`` reads ``metaschema.skipped()``), which is
#: why a change to one module's evaluation moves every golden.
NOT_EVALUATED = "CONSTRAINT_NOT_EVALUATED"

#: The vendored files by the bare names they carry under ``vendor/oscal/``.
#: ``snapshot.VENDORED_FILES`` lists them relative to ``vendor/`` (``oscal/<name>``);
#: if it ever lists anything else, this harness refuses to start rather than
#: looking for files under names that no longer mean what they meant.
if not VENDORED_FILES or any(Path(entry).parent != Path("oscal") for entry in VENDORED_FILES):
    raise RuntimeError(  # pragma: no cover - holds while snapshot.py's own test holds
        f"snapshot.VENDORED_FILES is not a list of oscal/<name>: {VENDORED_FILES}"
    )
NAMES: tuple[str, ...] = tuple(Path(entry).name for entry in VENDORED_FILES)

#: Run in a subprocess against a package directory. It refuses to answer unless
#: the package it imported is the one it was pointed at.
INVENTORY_SCRIPT = r"""
import hashlib, json, sys
from pathlib import Path
import oscal_validate
wanted = Path(sys.argv[1]).resolve()
loaded = Path(oscal_validate.__file__).resolve().parent.parent
if loaded != wanted:
    sys.exit(f"the inventory imported the package at {loaded}, not the copy at {wanted}")
from oscal_validate.metaschema import EVALUATED_KINDS, VALUE_KINDS, load_metaschema
from oscal_validate.schema import load_schema, schema_release

def parsed(constraint):
    if constraint.kind in EVALUATED_KINDS:
        return constraint.paths is not None
    if constraint.kind in VALUE_KINDS:
        return constraint.value_target is not None
    return None

raw = load_schema().raw
definitions = raw.get("definitions") or raw.get("$defs") or {}
print(json.dumps({
    "release": schema_release(),
    "constraints": [
        {
            "kind": c.kind, "identifier": c.identifier, "level": c.level, "module": c.module,
            "context": c.context, "target": c.target, "evaluated": c.evaluated,
            "skipped": c.skipped, "target_parsed": parsed(c),
        }
        for c in load_metaschema().constraints
    ],
    "definitions": {
        name: hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        for name, body in definitions.items()
    },
}, sort_keys=True))
"""


class RevendorError(RuntimeError):
    """The candidate was refused; the message says which file and why."""


class Fetches(Protocol):
    """What this harness needs from ``tools/fetch.py``'s ``Fetcher``."""

    def fetch(self, url: str) -> Any: ...


@dataclass(frozen=True)
class FileRecord:
    name: str
    sha256: str
    size: int
    source: str
    fetched_at: str


@dataclass
class Candidate:
    directory: Path
    files: dict[str, FileRecord] = field(default_factory=dict)


def original_name(vendored: str) -> str:
    return RENAMED.get(vendored, vendored)


def _refuse_markup(name: str, data: bytes) -> None:
    for marker in FORBIDDEN_MARKUP:
        if marker in data:
            raise RevendorError(
                f"{name} carries {marker.decode()}, so it is refused before anything reads it; "
                "the vendored files are parsed with the standard library, which a DTD can attack"
            )


def _record(name: str, data: bytes, source: str, fetched_at: str) -> FileRecord:
    return FileRecord(name, hashlib.sha256(data).hexdigest(), len(data), source, fetched_at)


def from_directory(directory: Path) -> Candidate:
    """A candidate already on disk, under the vendored names or NIST's original ones."""
    candidate = Candidate(directory)
    for name in NAMES:
        path = next(
            (p for p in (directory / name, directory / original_name(name)) if p.is_file()), None
        )
        if path is None:
            raise RevendorError(f"{directory} has no {name} (or {original_name(name)})")
        data = path.read_bytes()
        _refuse_markup(name, data)
        candidate.files[name] = _record(name, data, str(path), "-")
    return candidate


def by_fetch(
    version: str, fetcher: Fetches, into: Path, release_url: str = RELEASE_URL
) -> Candidate:
    """Every vendored file from NIST's release, through the robots-first fetcher."""
    candidate = Candidate(into)
    for name in NAMES:
        url = release_url.format(version=version, name=original_name(name))
        try:
            result = fetcher.fetch(url)
        except Exception as exc:  # FetchError and BlockedError are the fetcher's own
            raise RevendorError(f"{name}: {type(exc).__name__}: {exc}") from exc
        data: bytes = result.body
        _refuse_markup(name, data)
        (into / name).write_bytes(data)
        candidate.files[name] = _record(name, data, str(result.final_url), str(result.fetched_at))
    return candidate


# -- the copy and the inventory ----------------------------------------------


@contextmanager
def package_copy(candidate: Candidate) -> Iterator[Path]:
    """A throwaway copy of the package whose vendored files are the candidate's."""
    with tempfile.TemporaryDirectory(prefix="oscal-revendor-") as scratch:
        src = Path(scratch) / "src"
        copy = src / "oscal_validate"
        shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for name, record in candidate.files.items():
            data = (
                Path(record.source).read_bytes()
                if record.fetched_at == "-"
                else (candidate.directory / name).read_bytes()
            )
            (copy / "vendor" / "oscal" / name).write_bytes(data)
        yield src


def inventory(src: Path) -> dict[str, Any]:
    """The constraint and schema inventory of the package at ``src``, from its own reader."""
    result = subprocess.run(  # noqa: S603 - our own interpreter, our own script, no shell
        [sys.executable, "-c", INVENTORY_SCRIPT, str(src)],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(src), "PATH": "", "PYTHONHASHSEED": "0"},
    )
    if result.returncode != 0:
        raise RevendorError(
            "this tool's reader could not take the inventory of that snapshot:\n"
            + (result.stderr.strip().splitlines() or ["(no output)"])[-1]
        )
    loaded: dict[str, Any] = json.loads(result.stdout)
    return loaded


def keyed(constraints: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each constraint under a key no other constraint in the same snapshot shares.

    NIST reuses identifiers, so an identifier is not a key. In OSCAL 1.2.3 an
    ``index`` and the ``index-has-key`` that reads it carry one id, one id sits
    on two contexts, and seven unnamed ``allowed-values`` constraints in
    mapping-common agree on every field recorded here. The key is therefore
    module, identifier, kind and context, and whatever is still shared takes its
    position in document order.

    It deliberately leaves out ``target``, ``level`` and whether the constraint
    is evaluated, because those are the changes the diff reports. A key that
    contains a field turns every change of that field into one constraint
    removed and another added -- the second version of this function put
    ``target`` in the key to stop the collapse above, and ``retargeted`` could
    then never populate. ``tests/test_revendor.py`` re-targets a constraint and
    requires that section to name it.

    This harness first keyed on the identifier alone, folded 340 constraints
    into 324 and printed the fold as the release -- a count describing a dict,
    not NIST's publication. The refusal below is what stops that recurring.
    """
    out: dict[str, dict[str, Any]] = {}
    seen: dict[str, int] = {}
    for constraint in constraints:
        base = (
            f"{constraint['module']}#{constraint['identifier'] or '-'}"
            f"|{constraint['kind']}|{constraint['context']}"
        )
        seen[base] = seen.get(base, 0) + 1
        out[base if seen[base] == 1 else f"{base}|{seen[base]}"] = constraint
    if len(out) != len(constraints):  # pragma: no cover - the ordinals above make every key new
        raise RevendorError(f"{len(constraints)} constraints were keyed into {len(out)}")
    return out


def diff(
    current: dict[str, Any],
    candidate: dict[str, Any],
    current_files: dict[str, str],
    candidate_files: dict[str, str],
) -> dict[str, Any]:
    """What differs between two snapshots: bytes, constraints and schema definitions.

    The bytes decide whether anything changed; the inventory explains what.
    The inventory records a constraint's kind, level, context, target and
    whether this tool evaluates it -- not, for instance, the values an
    ``allowed-values`` set permits -- so a release could change a module in
    ways no inventory row shows. ``files`` is what keeps that from reading as
    "no change".
    """
    before = keyed(current["constraints"])
    after = keyed(candidate["constraints"])
    shared = sorted(set(before) & set(after))

    def changed(field_name: str) -> list[dict[str, Any]]:
        return [
            {"constraint": key, "from": before[key][field_name], "to": after[key][field_name]}
            for key in shared
            if before[key][field_name] != after[key][field_name]
        ]

    now_skipped = [
        {"constraint": k, "because": after[k]["skipped"]}
        for k in shared
        if before[k]["evaluated"] and not after[k]["evaluated"]
    ]
    now_evaluated = [k for k in shared if not before[k]["evaluated"] and after[k]["evaluated"]]
    retargeted = changed("target")
    moved_targets = {row["constraint"] for row in retargeted}
    added = sorted(set(after) - set(before))
    grammar = [
        {"constraint": k, "target": after[k]["target"], "because": after[k]["skipped"]}
        for k in sorted(set(added) | moved_targets)
        if after[k]["target_parsed"] is False
    ]
    old_defs, new_defs = current["definitions"], candidate["definitions"]
    return {
        "release": {"from": current["release"], "to": candidate["release"]},
        "files": {
            "changed": [
                {"file": name, "from": current_files[name], "to": candidate_files[name]}
                for name in sorted(set(current_files) & set(candidate_files))
                if current_files[name] != candidate_files[name]
            ],
        },
        "constraints": {
            # Counted from the lists as the parser returned them, never from a
            # keyed structure: a key that collides would otherwise change the
            # count, and the count is the claim.
            "published": {
                "from": len(current["constraints"]),
                "to": len(candidate["constraints"]),
            },
            "evaluated": {
                "from": sum(1 for c in current["constraints"] if c["evaluated"]),
                "to": sum(1 for c in candidate["constraints"] if c["evaluated"]),
            },
            "added": added,
            "removed": sorted(set(before) - set(after)),
            "relevelled": changed("level"),
            "retargeted": retargeted,
            "now_evaluated": now_evaluated,
            "now_skipped": now_skipped,
        },
        "outside_the_grammar": grammar,
        "definitions": {
            "added": sorted(set(new_defs) - set(old_defs)),
            "removed": sorted(set(old_defs) - set(new_defs)),
            "changed": sorted(
                k for k in set(old_defs) & set(new_defs) if old_defs[k] != new_defs[k]
            ),
        },
    }


def is_empty(change: dict[str, Any]) -> bool:
    constraints = change["constraints"]
    lists = [
        constraints[k]
        for k in ("added", "removed", "relevelled", "retargeted", "now_evaluated", "now_skipped")
    ]
    return (
        not change["files"]["changed"]
        and change["release"]["from"] == change["release"]["to"]
        and not any(lists)
        and not change["outside_the_grammar"]
        and not any(change["definitions"].values())
    )


def change_for(candidate: Candidate, src: Path) -> dict[str, Any]:
    """The whole diff for a candidate, whose package copy is at ``src``.

    The current side is read from this checkout's own ``src`` by the same
    subprocess reader as the candidate side, and the file hashes of the current
    side are computed from the vendored bytes, not read out of ``SOURCES.md``:
    a recorded hash says what was written down, a computed one says what the
    tool actually reads.
    """
    current = inventory(ROOT / "src")
    proposed = inventory(src)
    current_files = {
        name: hashlib.sha256((VENDOR / "oscal" / name).read_bytes()).hexdigest() for name in NAMES
    }
    candidate_files = {name: record.sha256 for name, record in candidate.files.items()}
    return diff(current, proposed, current_files, candidate_files)


# -- golden impact -----------------------------------------------------------

_CONSTRAINT_ID = re.compile(r"\b(oscal-[a-z0-9]+(?:-[a-z0-9]+)+)\b")


def _report(golden_bytes: bytes) -> dict[str, Any]:
    text = golden_bytes.decode("utf-8")
    loaded: dict[str, Any] = json.loads(text[: text.rindex("\n[exit")])
    return loaded


def golden_impact(src: Path) -> dict[str, Any]:
    """Every golden case run through the candidate copy, compared with its committed bytes."""
    # The denominator is about the *current* snapshot, which is the package this
    # harness itself runs on, so the in-process parser is the right one to ask.
    evaluated_ids = {c.identifier for c in load_metaschema().evaluated() if c.identifier}
    cases = [(name, document, resolve) for name, document, resolve in CASES]
    absent: list[str] = []
    for name, relative in CACHED:
        path = CACHE / relative
        if path.is_file():
            cases.append((name, path, []))
        else:
            absent.append(name)
    moved: list[dict[str, Any]] = []
    from_evaluated = findings = 0
    for name, document, resolve in cases:
        committed = {fmt: (GOLDEN / f"{name}.{fmt}.out").read_bytes() for fmt in ("text", "json")}
        report = _report(committed["json"])
        findings += len(report["findings"])
        from_evaluated += sum(
            1
            for f in report["findings"]
            if set(_CONSTRAINT_ID.findall(f["rule"]["citation"])) & evaluated_ids
        )
        candidate = {fmt: run(document, resolve, fmt, package=src) for fmt in ("text", "json")}
        if candidate == committed:
            continue
        comparison = compare(
            findings_from_report(report), findings_from_report(_report(candidate["json"]))
        ).to_dict()
        moved.append(
            {
                "golden": name,
                "formats": [fmt for fmt in ("text", "json") if candidate[fmt] != committed[fmt]],
                "findings": {k: len(v) for k, v in comparison.items() if isinstance(v, list)},
                # Every code that moved in any way, so the report can say *what*
                # moved rather than only that something did.
                "codes": sorted(
                    {f["code"] for f in comparison["added"] + comparison["removed"]}
                    | {
                        pair["after"]["code"]
                        for pair in comparison["changed"] + comparison["moved"]
                    }
                ),
            }
        )
    return {
        "cases_run": len(cases),
        "cases_not_run": absent,
        "moved": moved,
        "golden_findings": findings,
        "golden_findings_from_evaluated_constraints": from_evaluated,
    }


# -- writing -----------------------------------------------------------------


def _row(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"^(\| `oscal/{re.escape(name)}` \| [^|]+ \| `)([0-9a-f]{{64}})(` \|)$", re.M
    )


def write(candidate: Candidate, vendor: Path | None = None) -> list[str]:
    """Copy the candidate in and move each hash row. Every row is found before any byte moves."""
    # Bound at call time, not at definition time: a default of VENDOR would be
    # fixed when this module loads, and a test redirecting the vendored
    # directory would then write into the real one.
    vendor = VENDOR if vendor is None else vendor
    sources = vendor / "SOURCES.md"
    text = sources.read_text(encoding="utf-8")
    for name in candidate.files:
        found = len(_row(name).findall(text))
        if found != 1:
            raise RevendorError(f"SOURCES.md has {found} hash row(s) for oscal/{name}; expected 1")
    for name, record in candidate.files.items():
        text = _row(name).sub(rf"\g<1>{record.sha256}\g<3>", text)
        shutil.copyfile(
            Path(record.source) if record.fetched_at == "-" else candidate.directory / name,
            vendor / "oscal" / name,
        )
    sources.write_text(text, encoding="utf-8")
    return [
        "vendor/SOURCES.md: the release and retrieval date in the prose above the table",
        "tests/test_vendor_integrity.py: EXPECTED, the hand-kept copy of every hash",
        "src/oscal_validate/rules.py: OSCAL_RELEASE, RETRIEVED and SCHEMA_URL",
        "make coverage-doc, and make limits-data if the README's counts move",
        "tests/golden/capture.py, as its own commit with its reason, for every golden listed above",
        "the constraint survey (#46), against the new snapshot",
    ]


# -- rendering ---------------------------------------------------------------


def render_text(change: dict[str, Any], goldens: dict[str, Any], records: list[FileRecord]) -> str:
    c = change["constraints"]
    lines = [
        f"release: {change['release']['from']} -> {change['release']['to']}",
        f"files: {len(records)} read, every one checked for <!DOCTYPE and <!ENTITY",
        f"constraints published: {c['published']['from']} -> {c['published']['to']}; "
        f"evaluated: {c['evaluated']['from']} -> {c['evaluated']['to']}",
    ]
    changed_files = change["files"]["changed"]
    lines.append(f"files whose bytes differ: {len(changed_files)}")
    lines.extend(
        f"  {row['file']}: {row['from'][:12]} -> {row['to'][:12]}" for row in changed_files
    )
    for label, rows in (
        ("added", c["added"]),
        ("removed", c["removed"]),
        ("re-levelled", [f"{r['constraint']}: {r['from']} -> {r['to']}" for r in c["relevelled"]]),
        ("re-targeted", [f"{r['constraint']}: {r['from']} -> {r['to']}" for r in c["retargeted"]]),
        ("now evaluated", c["now_evaluated"]),
        ("now skipped", [f"{r['constraint']}: {r['because']}" for r in c["now_skipped"]]),
        (
            "outside the parsed grammar",
            [f"{r['constraint']}: {r['target']}" for r in change["outside_the_grammar"]],
        ),
        ("schema definitions added", change["definitions"]["added"]),
        ("schema definitions removed", change["definitions"]["removed"]),
        ("schema definitions changed", change["definitions"]["changed"]),
    ):
        lines.append(f"{label}: {len(rows)}")
        lines.extend(f"  {row}" for row in rows)
    explained = any(
        c[k]
        for k in ("added", "removed", "relevelled", "retargeted", "now_evaluated", "now_skipped")
    ) or any(change["definitions"].values())
    if changed_files and not explained:
        lines.append(
            "  the bytes differ in ways this inventory does not record (an allowed-values "
            "set, a description, a remark): read the file diff before calling this release "
            "unchanged"
        )
    lines.append(
        f"goldens: {goldens['cases_run']} run, {len(goldens['cases_not_run'])} not run "
        f"(cache absent: {', '.join(goldens['cases_not_run']) or 'none'}), "
        f"{len(goldens['moved'])} would move"
    )
    for row in goldens["moved"]:
        lines.append(f"  {row['golden']} ({', '.join(row['formats'])}): {', '.join(row['codes'])}")
    if goldens["moved"] and all(row["codes"] == [NOT_EVALUATED] for row in goldens["moved"]):
        lines.append(
            f"  in every one, the only finding that moved is {NOT_EVALUATED}: each report "
            "restates the release-wide count of constraints this tool does not evaluate, so a "
            "change in which constraints are evaluated moves every golden, whatever model it "
            "governs"
        )
    lines.append(
        f"  {goldens['golden_findings_from_evaluated_constraints']} of "
        f"{goldens['golden_findings']} golden finding(s) come from an evaluated constraint, "
        "so a change that reaches only those constraints can move no golden"
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tools/revendor.py",
        description=(
            "Diff a candidate OSCAL release against the vendored snapshot -- constraints, "
            "schema definitions, the parsed grammar and the goldens -- before anything is "
            "written. Writes only with --write, and only after the diff is printed."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "version", nargs="?", help="a NIST OSCAL release tag without the v, e.g. 1.2.4"
    )
    source.add_argument(
        "--from-dir", type=Path, help="a directory already holding the candidate files"
    )
    parser.add_argument(
        "--write", action="store_true", help="copy the candidate in, after the diff"
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Sequence[str] | None = None, fetcher: Fetches | None = None) -> int:
    args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    with tempfile.TemporaryDirectory(prefix="oscal-candidate-") as scratch:
        try:
            if args.from_dir is not None:
                candidate = from_directory(args.from_dir)
            else:
                if fetcher is None:
                    # Imported here, not at the top, so that the offline --from-dir
                    # path never loads the one module in this repository that opens
                    # a socket.
                    sys.path.insert(0, str(ROOT / "tools"))
                    from fetch import Fetcher  # noqa: PLC0415 - lazy on purpose, see above

                    fetcher = Fetcher()
                candidate = by_fetch(str(args.version), fetcher, Path(scratch))
            with package_copy(candidate) as src:
                change = change_for(candidate, src)
                goldens = golden_impact(src)
        except RevendorError as exc:
            print(f"tools/revendor.py: {exc}", file=sys.stderr)
            return 2
        records = list(candidate.files.values())
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "files": [record.__dict__ for record in records],
                        "change": change,
                        "goldens": goldens,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(render_text(change, goldens, records))
        if args.write:
            try:
                remaining = write(candidate)
            except RevendorError as exc:
                print(f"tools/revendor.py: {exc}", file=sys.stderr)
                return 2
            print("\nwritten. Still to do by hand, each a deliberate act:", file=sys.stderr)
            for step in remaining:
                print(f"  - {step}", file=sys.stderr)
    return 0 if is_empty(change) and not goldens["moved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
