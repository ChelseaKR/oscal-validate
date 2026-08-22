"""Command line interface.

The default command, ``oscal-validate <file.json>``, reads local files and
prints findings. It opens no network connection in any code path, makes no
model call, and produces the same bytes for the same input every time.
``tests/golden/`` holds those bytes.

The model-backed subcommands of ADR-0005 are dispatched by name before the
default parser sees the arguments, and the package that implements them is
imported only then; ``tests/test_default_path_byte_identity.py`` checks in a
fresh process that a validation run never loads it.

``--resolve`` takes more local files or directories. It is how an imported
catalog or profile gets into the effective data model, and it is the difference
between "this control reference resolves to nothing" and "this control
reference cannot be checked from here".

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
from .rules import OSCAL_RELEASE
from .schema import SchemaError
from .validator import build_session, validate

#: The subcommands of ADR-0005. Dispatched by name so the default parser, and
#: the default output, never see them; the package is imported only then.
AI_COMMANDS = ("explain", "repair", "walkthrough", "ask")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oscal-validate",
        description=(
            "Deterministic structural validation of OSCAL documents against NIST's "
            f"published schema and constraint layer for OSCAL {OSCAL_RELEASE}. Checks "
            "structure, identifiers, and reference resolution. It does not, and cannot, "
            "assess whether any control described in the document is implemented. No "
            "network calls, no model calls."
        ),
        epilog=(
            "Severities: ERROR gates the exit code. UNVERIFIABLE never does; it marks "
            "what the supplied documents cannot settle, and is never a pass. "
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
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in AI_COMMANDS:
        ai_cli = importlib.import_module("oscal_validate.ai.cli")
        result: int = ai_cli.main(arguments)
        return result
    args = build_parser().parse_args(arguments)
    try:
        session = build_session(Path(args.file), [Path(p) for p in args.resolve])
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
    print(
        render_findings_json(findings, __version__, model)
        if args.format == "json"
        else render_findings_text(findings, model)
    )
    return 1 if any(f.severity is Severity.ERROR for f in findings) else 0


def entrypoint() -> None:
    raise SystemExit(main())
