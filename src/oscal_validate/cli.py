"""Command line interface.

The default command, ``oscal-validate <file.json>``, reads local files and
prints findings. It opens no network connection in any code path, makes no
model call, and produces the same bytes for the same input every time.
``tests/golden/`` holds those bytes.

The model-backed subcommands of ADR-0005 are dispatched by name before the
default parser sees the arguments, and the package that implements them is
imported only then; ``tests/test_default_path_byte_identity.py`` checks in a
fresh process that a validation run never loads it.

``diff`` and ``rule`` are dispatched the same way but are not among them:
``diff`` compares two runs and ``rule`` prints the citation trail for one
constraint identifier or finding code, and both are as deterministic and as
offline as the default path.

``--resolve`` takes more local files or directories. It is how an imported
catalog or profile gets into the effective data model, and it is the difference
between "this control reference resolves to nothing" and "this control
reference cannot be checked from here".

``--format`` selects text (default), json (the canonical machine-readable
report), sarif (SARIF 2.1.0, the same findings for code-scanning viewers; see
``sarif.py`` for how severities map and why no result is ever a pass), or html
(one self-contained page for a reviewer, written to stdout like the others; see
``htmlreport.py``).

``--baseline`` reads a committed list of acknowledged findings. A finding it
names is still printed, still counted and still an ERROR; the one thing it
stops doing is gating the exit code. ``--write-baseline`` prints such a file
for a human to annotate, to stdout rather than to disk, because this command
has never written a file and the privacy audit says so. See ``baseline.py``.

Exit codes: 0 = no ERROR findings the baseline did not acknowledge; 1 = at
least one that it did not, or a stale baseline entry under
``--fail-on-stale``; 2 = the input, or the baseline, could not be read.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__, baseline
from .document import DocumentError
from .findings import Finding, render_findings_json, render_findings_text, stale_count
from .htmlreport import render_findings_html
from .positions import attach
from .report import read_report_schema
from .rules import OSCAL_RELEASE
from .sarif import render_findings_sarif
from .schema import SchemaError
from .validator import build_session, validate

#: The subcommands of ADR-0005. Dispatched by name so the default parser, and
#: the default output, never see them; the package is imported only then.
AI_COMMANDS = ("explain", "repair", "walkthrough", "ask")

#: Subcommands that are as deterministic and as offline as the default path.
#: Dispatched the same way and for the same reason -- the default parser takes
#: a file as its first positional, so a verb name would be read as a filename
#: -- but they load no optional dependency and reach no model.
#:
#: Each is imported below by a **literal** module path, the way the AI
#: subcommands are. Interpolating the argument into ``import_module`` works and
#: would let this tuple be the only place a verb is written down, but it also
#: means the first word of a command line names a module -- semgrep's
#: ``non-literal-import`` says so, and it is right that this is not a property
#: worth having to save a line. ``test_every_deterministic_command_is_actually
#: _dispatched`` holds the tuple and the branches together instead.
DETERMINISTIC_COMMANDS = ("diff", "rule")


class PrintReportSchema(argparse.Action):
    """Print the published report schema and exit, the way ``--version`` does.

    An action rather than a subcommand: it takes no argument and answers
    before the required positional is missed, so ``oscal-validate
    --report-schema`` needs no document.
    """

    def __init__(self, option_strings: Sequence[str], dest: str, **kwargs: object) -> None:
        super().__init__(option_strings=list(option_strings), dest=dest, nargs=0, **kwargs)  # type: ignore[arg-type]

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        print(read_report_schema(), end="")
        parser.exit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oscal-validate",
        description=(
            "Deterministic structural validation of OSCAL documents against NIST's "
            f"published schema and constraint layer for OSCAL {OSCAL_RELEASE}. Checks "
            "structure, identifiers, and reference resolution. It does not, and cannot, "
            "assess whether any control described in the document is implemented. This "
            "command makes no network call and no model call."
        ),
        epilog=(
            "Severities: ERROR gates the exit code. UNVERIFIABLE never does; it marks "
            "what the supplied documents cannot settle, and is never a pass. "
            f"`oscal-validate {DETERMINISTIC_COMMANDS[0]} --help` compares two runs and "
            f"`oscal-validate {DETERMINISTIC_COMMANDS[1]} --help` prints the citation "
            "trail for one constraint or finding code, both with no model and no "
            "network, like this command. "
            f"Opt-in model-backed subcommands ({', '.join(AI_COMMANDS)}) are documented by "
            "`oscal-validate explain --help`; they call a model, this command never does."
        ),
    )
    parser.add_argument("file", help="path to an OSCAL JSON document")
    parser.add_argument(
        "--resolve",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "a further OSCAL document, or a directory of them, to resolve imports and "
            "references against. Repeatable. Nothing is fetched."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "sarif", "html"),
        default="text",
        help=(
            "output format (default: text). sarif is SARIF 2.1.0 with the same findings: "
            "ERROR and WARNING as kind fail, UNVERIFIABLE as kind open, never a pass. "
            "html is one self-contained page for a reviewer -- no script, no external "
            "stylesheet, no timestamp -- written to stdout like the others"
        ),
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help=(
            "beneath a reference that resolves to nothing, name up to three identifiers "
            "that ARE declared and are within a bounded edit distance of the one written. "
            "Computed offline from the documents supplied; never offered for an "
            "UNVERIFIABLE reference, and never asserted to be what was meant. Off by "
            "default: without it this command's bytes are unchanged."
        ),
    )
    parser.add_argument(
        "--locations",
        action="store_true",
        help=(
            "print the line and column in the source file where each finding's pointer "
            "points, beside the pointer and never instead of it. text gains "
            "'<file>:<line>:<column>' on a finding's first line; json gains line and "
            "column on every finding, null where this run has no position for that "
            "pointer -- never 0, which is a line no file has. sarif and html are "
            "unchanged by this flag today. Off by default: without it this command's "
            "bytes are unchanged, and no source index is built"
        ),
    )
    parser.add_argument(
        "--baseline",
        metavar="FILE",
        help=(
            "a committed list of acknowledged findings, each with a written reason and "
            "the date it was acknowledged. Findings it names are still printed, still "
            "counted, and marked ACKNOWLEDGED, but do not gate the exit code; everything "
            "else gates exactly as it does without this flag. An entry that matches "
            "nothing is reported as BASELINE_STALE. An entry with no reason, or one that "
            "names an UNVERIFIABLE finding, is refused (exit 2)"
        ),
    )
    parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help=(
            "exit 1 when a --baseline entry matched nothing in this run, so a baseline "
            "cannot outlive the defect it excused"
        ),
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help=(
            "print a baseline document for this run instead of the report, for a human "
            "to annotate with reasons. It is written to stdout rather than to a file: "
            "this tool has never written to disk and the privacy audit says so. As "
            "generated it is refused by --baseline, because every entry needs a reason. "
            "Exits 0 whatever the findings were; it generates, it does not gate"
        ),
    )
    parser.add_argument(
        "--report-schema",
        action=PrintReportSchema,
        help=(
            "print the JSON Schema that every --format json report conforms to, and exit. "
            "The report carries the schema's version in report_schema_version"
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in AI_COMMANDS:
        ai_cli = importlib.import_module("oscal_validate.ai.cli")
        result: int = ai_cli.main(arguments)
        return result
    if arguments and arguments[0] == "diff":
        diff_cli = importlib.import_module("oscal_validate.diff")
        verdict: int = diff_cli.main(arguments)
        return verdict
    if arguments and arguments[0] == "rule":
        rule_cli = importlib.import_module("oscal_validate.rule")
        trail: int = rule_cli.main(arguments)
        return trail
    args = build_parser().parse_args(arguments)
    try:
        session = build_session(
            Path(args.file),
            [Path(p) for p in args.resolve],
            suggest=args.suggest,
            locations=args.locations,
        )
        findings = validate(session)
    except (DocumentError, SchemaError) as exc:
        print(f"oscal-validate: {exc}", file=sys.stderr)
        return 2
    except RecursionError:
        print(
            f"oscal-validate: {args.file} nests too deeply to read safely",
            file=sys.stderr,
        )
        return 2

    if args.write_baseline:
        print(baseline.render(findings))
        return 0

    used = str(args.baseline or "")
    if used:
        try:
            findings = baseline.apply(findings, baseline.load(Path(used)))
        except baseline.BaselineError as exc:
            print(f"oscal-validate: {exc}", file=sys.stderr)
            return 2
        # A BASELINE_STALE finding is made after `validate` returned, so it
        # has no position yet. Attaching again is idempotent for every other
        # finding and is what stops one row of a --locations report reading
        # as positionless for a reason that has nothing to do with the file.
        findings = attach(findings, session.corpus)

    _render(
        findings,
        args.format,
        session.corpus.primary.walked.model,
        args.file,
        [str(p) for p in args.resolve],
        used,
        locations=args.locations,
    )
    return _exit_code(findings, fail_on_stale=args.fail_on_stale)


def _render(
    findings: list[Finding],
    fmt: str,
    model: str,
    document: str,
    resolve: list[str],
    baseline_path: str,
    *,
    locations: bool = False,
) -> None:
    """Write the report. ``locations`` reaches text and json and nothing else.

    sarif and html do not carry a position today. That is a gap rather than a
    decision, and it is stated in ``--locations``' own help text and pinned by
    ``tests/test_locations.py`` so the flag cannot look like it did something
    to a format it did not touch.
    """
    if fmt == "json":
        print(
            render_findings_json(findings, __version__, model, baseline_path, locations=locations)
        )
    elif fmt == "sarif":
        print(render_findings_sarif(findings, __version__, model, Path(document)))
    elif fmt == "html":
        print(
            render_findings_html(
                findings,
                __version__,
                model,
                Path(document),
                [Path(p) for p in resolve],
                baseline_path,
            ),
            end="",
        )
    else:
        print(render_findings_text(findings, model, baseline_path, locations=locations))


def _exit_code(findings: list[Finding], *, fail_on_stale: bool) -> int:
    """0 or 1, and the only place either is decided.

    ``Finding.gates`` is what makes an acknowledged ERROR not gate; it is a
    property of the finding rather than a filter written here, so every reader
    of a finding gets the same answer. A stale baseline entry gates only when
    it was asked to, because the document may simply have been fixed.
    """
    if any(finding.gates for finding in findings):
        return 1
    if fail_on_stale and stale_count(findings):
        return 1
    return 0


def entrypoint() -> None:
    raise SystemExit(main())
