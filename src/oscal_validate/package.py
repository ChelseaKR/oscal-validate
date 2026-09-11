"""``oscal-validate package`` -- a directory validated as one deliverable.

A FedRAMP or agency package is a directory: an SSP, the profile it imports, the
catalog behind that, component definitions, assessment plans and results.
Validating each file alone, with a hand-assembled ``--resolve`` list, answers a
smaller question than the one a reviewer is asking. This verb takes the
directory as the thing being validated.

**It is exactly N runs of the command line, plus what only a set can show.**
Every member is validated with every other member as its resolve set -- the
documents ``oscal-validate <member> --resolve <directory>`` would read -- and
through the same composition function the command line reaches, so a member's
report is not merely expected to match that command's: it is produced by the
same code over the same inputs, and ``tests/test_package.py`` compares the two
byte for byte. What this adds is what no single run can see: the import graph
across the set, the imports naming a file the set does not contain, the imports
more than one member answers to, the members nothing imports, and UUIDs
declared in more than one member.

**It fails closed.** A member that cannot be read -- not JSON, not an OSCAL
document, nested too deeply -- would make every one of those N runs exit 2,
because each of them would try to read it as a resolve candidate. So this verb
exits 2 as well, names every such file with its reason on stderr, and writes no
report. The alternative is worse than it looks: validating the rest against a
set that silently lost a member would publish ``IMPORT_NOT_SUPPLIED`` -- "No
document with this file name was supplied" -- about a file that *was* supplied
and could not be read, and a report with a short document list is exactly what
a smaller clean package looks like. An empty directory is exit 2 too: a package
with nothing in it has not been found clean.

**The cross-document sections never gate.** They are observations about the
set, not findings in any document: the exit code is the command line's own
verdict over the members, and nothing else. UUID collisions in particular are
stated as package policy. Check 4 applies NIST's sentence that OSCAL's UUIDs
"are always globally-unique" within one document; whether a UUID declared in
two members of one package is a defect is for a reviewer of that package to
decide, so it is listed with every place it is declared and never counted.

**There is no "ambiguous imports" section, on purpose.** Issue #60 asked for
one. Import matching keys on a file name and then on the file name without its
extension, and within one directory no two ``.json`` files can share either,
so no import can resolve to more than one member here. A section that could
only ever print "none" would read as a check that looked and found nothing.
``IMPORT_AMBIGUOUS`` stays in the per-document report, where ``--resolve`` over
several directories can still produce it.

**What it deliberately does not do yet.** The GitHub Action does not run this
verb: its ``path`` input still validates each document on its own, with the
resolve list the caller gives it. Teaching it package mode changes a published
Action's inputs and the report shape its runner reads, and belongs in its own
change; ``--help`` says so, and ``tests/test_package.py`` fails if ``action.yml``
gains a ``mode`` input without that sentence moving.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .checks.identifiers import uuid_definitions
from .corpus import Corpus, ImportEdge, LoadedDocument, collect_paths, compose, load_document
from .document import DocumentError
from .findings import (
    SEVERITY_ORDER,
    Finding,
    counts,
    exit_code,
    render_findings_json,
    render_findings_text,
)
from .metaschema import load_metaschema
from .schema import SchemaError, load_schema
from .session import Session
from .validator import validate

#: The version of ``package.schema.json``, stamped into every package report.
#: Moves by the same rule as the per-document report's version (see
#: ``report.py``), and independently of it: a member's embedded report carries
#: its own ``report_schema_version``, which this one does not restate.
PACKAGE_SCHEMA_VERSION = "1.0.0"

#: The schema, shipped as package data beside this module.
PACKAGE_SCHEMA_PATH = Path(__file__).resolve().parent / "package.schema.json"

#: Fixed sentences every JSON package report carries, so a consumer that never
#: reads this module still meets what the cross-document sections do not mean.
NOTES = {
    "cross_document_sections": (
        "Every section other than documents is an observation about the set. None "
        "of them gates the exit code, and none is a finding in any document's report."
    ),
    "uuid_collisions": (
        "Package policy, not a finding. NIST's constraint layer checks UUID uniqueness "
        "within one document, and so does this tool. A UUID declared in more than one "
        "member is listed with every place it is declared; whether that is a defect is "
        "for a reviewer of the package to decide."
    ),
    "unreferenced": (
        "Members that no other member imports. A package's top-level document, usually "
        "its system security plan, is always among them: this is a map of the set's "
        "roots, not a list of defects."
    ),
}


class PackageError(ValueError):
    """The directory could not be taken as a package; the message says why."""


@dataclass(frozen=True)
class Unread:
    """A file in the directory that could not be read, with the reason."""

    path: str
    reason: str


class Unreadable(PackageError):
    """At least one member could not be read, so no member was validated."""

    def __init__(self, directory: str, unread: tuple[Unread, ...], examined: int) -> None:
        self.directory = directory
        self.unread = unread
        self.examined = examined
        super().__init__(self.render())

    def render(self) -> str:
        lines = [
            f"oscal-validate package: {len(self.unread)} of {self.examined} file(s) in "
            f"{self.directory} could not be read, so no member was validated.",
        ]
        lines.extend(f"  {item.path}: {item.reason}" for item in self.unread)
        lines.append(
            "Every member is validated against every other, so a set that silently "
            "lost one would report imports of it as not supplied. Fix or remove each "
            "file above, or point this command at a directory holding only the "
            "package, and run it again."
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class Member:
    """One document of the package, and its report against the others."""

    document: LoadedDocument
    corpus: Corpus
    findings: tuple[Finding, ...]

    @property
    def path(self) -> str:
        return self.document.path

    @property
    def model(self) -> str:
        return self.document.walked.model

    @property
    def edges(self) -> tuple[ImportEdge, ...]:
        """This member's own imports, not the ones reached through them.

        Selected by the document each edge was recorded in, never by parsing
        its pointer: a pointer into a supporting document is qualified with
        that document's path, and an absolute path begins with ``/`` exactly as
        a bare pointer does.
        """
        return tuple(edge for edge in self.corpus.edges if edge.source == self.path)


@dataclass(frozen=True)
class Collision:
    """One UUID declared in more than one member."""

    uuid: str
    #: ``(member path, pointer)`` for every declaration, sorted.
    declared_at: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Package:
    root: str
    members: tuple[Member, ...]

    def import_graph(self) -> tuple[ImportEdge, ...]:
        return tuple(edge for member in self.members for edge in member.edges)

    def imports_not_in_package(self) -> tuple[ImportEdge, ...]:
        """Imports whose name no member answers to, not even by stem."""
        return tuple(edge for edge in self.import_graph() if not edge.candidates)

    def unreferenced(self) -> tuple[str, ...]:
        imported = {
            edge.resolved_to
            for member in self.members
            for edge in member.edges
            if edge.resolved_to is not None and edge.resolved_to != member.path
        }
        return tuple(member.path for member in self.members if member.path not in imported)

    def uuid_collisions(self) -> tuple[Collision, ...]:
        declared: dict[str, list[tuple[str, str]]] = {}
        for member in self.members:
            for scalar in uuid_definitions(member.document.walked):
                declared.setdefault(str(scalar.value), []).append((member.path, scalar.pointer))
        return tuple(
            Collision(uuid=value, declared_at=tuple(sorted(places)))
            for value, places in sorted(declared.items())
            if len({path for path, _ in places}) > 1
        )

    def verdict(self) -> int:
        """The command line's own exit code over the members, and nothing else.

        ``findings.exit_code`` decides each member exactly as it decides a
        single run; the cross-document sections take no part in it.
        """
        return max(exit_code(list(member.findings)) for member in self.members)


def read_package(directory: Path, *, locations: bool = False) -> Package:
    """Read every member once, then validate each against the rest.

    Raises :class:`PackageError` for a path that is not a directory or holds
    no ``.json`` file, and :class:`Unreadable` when any member cannot be read.
    The member set is :func:`~oscal_validate.corpus.collect_paths` over the
    directory -- the same set ``--resolve <directory>`` supplies -- so the two
    cannot disagree about which files a package contains.
    """
    if not directory.is_dir():
        raise PackageError(f"{directory} is not a directory")
    paths = collect_paths([directory])
    if not paths:
        raise PackageError(
            f"{directory} holds no .json file. A package with nothing in it has not "
            "been found clean."
        )
    schema = load_schema()
    loaded: list[LoadedDocument] = []
    unread: list[Unread] = []
    for path in paths:
        try:
            loaded.append(load_document(path, schema, locations=locations))
        except DocumentError as exc:
            unread.append(Unread(str(path), str(exc)))
        except RecursionError:
            unread.append(Unread(str(path), f"{path} nests too deeply to read safely"))
    if unread:
        raise Unreadable(str(directory), tuple(unread), len(paths))

    metaschema = load_metaschema()
    members: list[Member] = []
    too_deep: list[Unread] = []
    for document in loaded:
        corpus = compose(document, tuple(other for other in loaded if other is not document))
        session = Session(corpus=corpus, schema=schema, metaschema=metaschema)
        try:
            findings = tuple(validate(session))
        except RecursionError:
            # A document can decode and still nest too deeply for the
            # constraint layer's descendant walk: measured at 4,000 levels, the
            # decoder reads it and ``metaschema._walk_descendants`` is what
            # recurses. The command line reports that as exit 2 in the same
            # words, so the package does too, naming the member. Left
            # unguarded it left as a traceback with exit code 1, which this
            # tool's contract reserves for "an ERROR was found".
            too_deep.append(
                Unread(document.path, f"{document.path} nests too deeply to read safely")
            )
            continue
        members.append(Member(document=document, corpus=corpus, findings=findings))
    if too_deep:
        raise Unreadable(str(directory), tuple(too_deep), len(paths))
    return Package(root=str(directory), members=tuple(members))


# -- rendering ---------------------------------------------------------------


def _edge(edge: ImportEdge) -> dict[str, object]:
    return {
        "from": edge.source,
        "pointer": edge.pointer,
        "href": edge.href,
        "target_name": edge.target_name,
        "resolved_to": edge.resolved_to,
        "matched_by": edge.matched_by or None,
        "candidates": list(edge.candidates),
    }


def _totals(package: Package) -> dict[str, int]:
    return {
        severity.value: sum(
            counts(list(member.findings))[severity.value] for member in package.members
        )
        for severity in SEVERITY_ORDER
    }


def render_json(package: Package, *, locations: bool = False) -> str:
    """The package report. Each member's ``report`` is the CLI's, parsed."""
    documents = [
        {
            "path": member.path,
            "model": member.model,
            "exit_code": exit_code(list(member.findings)),
            "report": json.loads(
                render_findings_json(
                    list(member.findings), __version__, member.model, locations=locations
                )
            ),
        }
        for member in package.members
    ]
    payload: dict[str, object] = {
        "package_report_schema_version": PACKAGE_SCHEMA_VERSION,
        "tool": {"name": "oscal-validate", "version": __version__},
        "package": {"root": package.root, "documents": len(package.members)},
        "documents": documents,
        "import_graph": [_edge(edge) for edge in package.import_graph()],
        "imports_not_in_package": [_edge(edge) for edge in package.imports_not_in_package()],
        "unreferenced": list(package.unreferenced()),
        "uuid_collisions": [
            {
                "uuid": collision.uuid,
                "declared_at": [
                    {"path": path, "location": pointer} for path, pointer in collision.declared_at
                ],
            }
            for collision in package.uuid_collisions()
        ],
        "summary": {
            **_totals(package),
            "documents": len(package.members),
            "imports_not_in_package": len(package.imports_not_in_package()),
            "unreferenced": len(package.unreferenced()),
            "uuid_collisions": len(package.uuid_collisions()),
        },
        "notes": NOTES,
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def _edge_line(edge: ImportEdge) -> str:
    if edge.resolved_to is not None:
        return (
            f"  {edge.source} {edge.pointer} -> {edge.resolved_to} (matched by {edge.matched_by})"
        )
    return f"  {edge.source} {edge.pointer} -> {edge.href}: no member of this package answers to it"


def _section(title: str, rows: list[str]) -> list[str]:
    if not rows:
        return [f"{title}: none"]
    return [f"{title} ({len(rows)}):", *rows]


def render_text(package: Package, *, locations: bool = False) -> str:
    """Each member's text report, verbatim, then what only the set shows."""
    lines = [f"package: {package.root} ({len(package.members)} document(s))", ""]
    for member in package.members:
        lines.append(f"== {member.path} ==")
        lines.append(render_findings_text(list(member.findings), member.model, locations=locations))
        lines.append("")
    lines.append("== across the package ==")
    lines.extend(_section("imports", [_edge_line(edge) for edge in package.import_graph()]))
    lines.extend(
        _section(
            "imports naming a file this package does not contain",
            [_edge_line(edge) for edge in package.imports_not_in_package()],
        )
    )
    lines.extend(
        _section(
            "members no other member imports", [f"  {path}" for path in package.unreferenced()]
        )
    )
    lines.extend(
        _section(
            "UUIDs declared in more than one member (package policy, not a finding)",
            [
                f"  {collision.uuid}: "
                + "; ".join(f"{path} at {pointer}" for path, pointer in collision.declared_at)
                for collision in package.uuid_collisions()
            ],
        )
    )
    totals = _totals(package)
    summary = ", ".join(f"{totals[severity.value]} {severity.value}" for severity in SEVERITY_ORDER)
    lines.append("")
    lines.append(
        f"{len(package.members)} document(s): {summary}. Nothing under "
        "'across the package' gates the exit code."
    )
    return "\n".join(lines)


# -- the command -------------------------------------------------------------


def read_package_schema() -> str:
    """The package schema as published, byte for byte."""
    return PACKAGE_SCHEMA_PATH.read_text(encoding="utf-8")


class PrintPackageSchema(argparse.Action):
    """Print the package schema and exit, before the directory is missed."""

    def __init__(self, option_strings: Sequence[str], dest: str, **kwargs: object) -> None:
        super().__init__(option_strings=list(option_strings), dest=dest, nargs=0, **kwargs)  # type: ignore[arg-type]

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        print(read_package_schema(), end="")
        parser.exit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oscal-validate package",
        description=(
            "Validate a directory of OSCAL JSON documents as one deliverable: every "
            "member is validated with every other as its resolve set, exactly as "
            "'oscal-validate <member> --resolve <directory>' would, and the report adds "
            "the import graph across the set, the imports naming a file it does not "
            "contain, the imports more than one member answers to, the members nothing "
            "imports, and UUIDs declared in more than one member. Offline, "
            "deterministic, no model call."
        ),
        epilog=(
            "Exit codes are the command line's: 0 when no member has an ERROR, 1 when "
            "one does, and 2 when the directory is empty, is not a directory, or holds a "
            "file that cannot be read -- every such file is named, and no member is "
            "validated against a set that lost one. The cross-document sections never "
            "gate. The GitHub Action does not run this verb yet: its `path` input still "
            "validates each document on its own."
        ),
    )
    parser.add_argument("directory", help="the directory holding the package's documents")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help=(
            "output format (default: text). json conforms to the package schema, and "
            "each member's embedded report to the per-document report schema"
        ),
    )
    parser.add_argument(
        "--locations",
        action="store_true",
        help="add the line and column to every member's findings, as --locations does",
    )
    parser.add_argument(
        "--report-schema",
        action=PrintPackageSchema,
        help="print the JSON Schema every --format json package report conforms to, and exit",
    )
    return parser


def main(argv: Sequence[str]) -> int:
    args = build_parser().parse_args(list(argv)[1:])
    try:
        package = read_package(Path(args.directory), locations=args.locations)
    except Unreadable as exc:
        print(exc.render(), file=sys.stderr)
        return 2
    except (PackageError, SchemaError) as exc:
        print(f"oscal-validate package: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(render_json(package, locations=args.locations))
    else:
        print(render_text(package, locations=args.locations))
    return package.verdict()
