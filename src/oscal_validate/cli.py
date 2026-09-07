"""Command line interface.

The default command, ``oscal-validate <file.json>``, reads local files and
prints findings. It opens no network connection in any code path, makes no
model call, and produces the same bytes for the same input every time.
``tests/golden/`` holds those bytes.

The model-backed subcommands of ADR-0005 are dispatched by name before the
default parser sees the arguments, and the package that implements them is
imported only then; ``tests/test_default_path_byte_identity.py`` checks in a
fresh process that a validation run never loads it.

``diff`` is dispatched the same way but is not one of them: it compares two
runs and is as deterministic and as offline as the default path.

``--resolve`` takes more local files or directories. It is how an imported
catalog or profile gets into the effective data model, and it is the difference
between "this control reference resolves to nothing" and "this control
reference cannot be checked from here".

``--format`` selects text (default), json (the canonical machine-readable
report), or sarif (SARIF 2.1.0, the same findings for code-scanning viewers;
see ``sarif.py`` for how severities map and why no result is ever a pass).

Exit codes: 0 = no ERROR findings; 1 = at least one ERROR finding; 2 = the
input could not be read or parsed at all.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .document import DocumentError
from .findings import Severity, render_findings_json, render_findings_text
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
DETERMINISTIC_COMMANDS = ("diff",)


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
            f"`oscal-validate {DETERMINISTIC_COMMANDS[0]} --help` compares two runs, with "
            "no model and no network, like this command. "
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
        choices=("text", "json", "sarif"),
        default="text",
        help=(
            "output format (default: text). sarif is SARIF 2.1.0 with the same findings: "
            "ERROR and WARNING as kind fail, UNVERIFIABLE as kind open, never a pass"
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
    args = build_parser().parse_args(arguments)
    try:
        session = build_session(
            Path(args.file), [Path(p) for p in args.resolve], suggest=args.suggest
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

    model = session.corpus.primary.walked.model
    if args.format == "json":
        print(render_findings_json(findings, __version__, model))
    elif args.format == "sarif":
        print(render_findings_sarif(findings, __version__, model, Path(args.file)))
    else:
        print(render_findings_text(findings, model))
    return 1 if any(f.severity is Severity.ERROR for f in findings) else 0


def entrypoint() -> None:
    raise SystemExit(main())
