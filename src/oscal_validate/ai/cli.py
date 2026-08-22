"""The opt-in subcommands. Reached only by name, imported only then.

``oscal-validate explain <file>``, ``repair --draft``, ``walkthrough``, and
``ask`` share this parser. Each starts by running the deterministic
validator; each prints a banner saying that what follows is AI-generated
and what was checked before it was shown; each exits 0 when it produced
its output, 2 when the document could not be read or the model could not
be reached, and never gates on a finding, because the findings are the
validator's job and the default command already does that.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ..document import DocumentError
from ..findings import Severity
from ..schema import SchemaError
from . import ask as ask_command
from . import explain as explain_command
from .client import ModelClient, ModelError, build_client
from .run import Run, banner, prepare

COMMANDS = ("explain", "repair", "walkthrough", "ask")

_SEVERITIES = [s.value for s in Severity]


def _selection(parser: argparse.ArgumentParser, verb: str, default_limit: int) -> None:
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="F3",
        help=f"{verb} this finding by its label in the validator's order; repeatable",
    )
    parser.add_argument("--code", action="append", default=[], help="only findings with this code")
    parser.add_argument(
        "--severity",
        action="append",
        default=[],
        choices=_SEVERITIES,
        help="only findings at this severity (default: ERROR and WARNING)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=default_limit,
        help=f"at most this many model calls (default {default_limit})",
    )


def _common(parser: argparse.ArgumentParser, document: bool = True) -> None:
    if document:
        parser.add_argument("file", help="path to an OSCAL JSON document")
    parser.add_argument(
        "--resolve",
        action="append",
        default=[],
        metavar="PATH",
        help="further documents or directories, as for the default command",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--provider",
        choices=("anthropic", "bedrock"),
        help="overrides OSCAL_VALIDATE_AI_PROVIDER",
    )
    parser.add_argument("--model", help="overrides OSCAL_VALIDATE_AI_MODEL")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oscal-validate",
        description=(
            "Opt-in, model-backed commands (ADR-0005). Each runs the deterministic validator "
            "first and works only from its findings and from NIST's published text. A model "
            "call leaves this machine with the findings, passages of NIST documentation, and "
            "excerpts of the document. The default command makes no such call."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    explain = sub.add_parser(
        "explain", help="explain findings in plain language, grounded in NIST's text"
    )
    _common(explain)
    _selection(explain, "explain", 5)

    ask = sub.add_parser(
        "ask", help="what a constraint requires and why NIST has it, from NIST's own text"
    )
    ask.add_argument("question", help="a question about OSCAL's published rules")
    ask.add_argument(
        "--document",
        metavar="FILE",
        help="an OSCAL document to validate first; its findings are given to the model",
    )
    _common(ask, document=False)
    return parser


def _environ(args: argparse.Namespace) -> dict[str, str]:
    env = dict(os.environ)
    if args.provider:
        env["OSCAL_VALIDATE_AI_PROVIDER"] = args.provider
    if args.model:
        env["OSCAL_VALIDATE_AI_MODEL"] = args.model
    return env


def _select(run: Run, args: argparse.Namespace) -> list[int]:
    """Indexes of the findings to explain, in report order."""
    if args.label:
        wanted = set(args.label)
        return [i for i, f in enumerate(run.findings) if run.label(f) in wanted]
    severities = set(args.severity) or {"ERROR", "WARNING"}
    codes = set(args.code)
    chosen = [
        i
        for i, f in enumerate(run.findings)
        if f.severity.value in severities and (not codes or f.code in codes)
    ]
    return chosen[: max(0, args.limit)]


def _prepare_or_exit(args: argparse.Namespace, file: str | None = None) -> Run | None:
    try:
        return prepare(Path(file or args.file), [Path(p) for p in args.resolve])
    except (DocumentError, SchemaError) as exc:
        print(f"oscal-validate: {exc}", file=sys.stderr)
        print(
            "oscal-validate: the validator could not read this document, so there is nothing "
            "honest to explain about it",
            file=sys.stderr,
        )
        return None


def _client_or_exit(args: argparse.Namespace) -> ModelClient | None:
    try:
        return build_client(_environ(args))
    except ModelError as exc:
        print(f"oscal-validate: {exc}", file=sys.stderr)
        return None


def _explain(args: argparse.Namespace) -> int:
    run = _prepare_or_exit(args)
    if run is None:
        return 2
    client = _client_or_exit(args)
    if client is None:
        return 2
    selected = _select(run, args)
    explanations = [explain_command.explain_one(run, run.findings[i], client) for i in selected]
    if args.format == "json":
        print(json.dumps(explain_command.render_json(explanations, client, run), indent=2))
        return 0
    print(banner(client))
    print(f"model: {run.model}; {len(run.findings)} finding(s), {len(selected)} explained\n")
    if not selected:
        print("no finding matched the selection; nothing was sent to the model")
    for explanation in explanations:
        print(explain_command.render_text(explanation))
        print()
    return 0


def _ask(args: argparse.Namespace) -> int:
    run: Run | None = None
    if args.document:
        run = _prepare_or_exit(args, args.document)
        if run is None:
            return 2
    client = _client_or_exit(args)
    if client is None:
        return 2
    answer = ask_command.ask_one(args.question, client, run)
    if args.format == "json":
        print(json.dumps(ask_command.render_json(answer, client, run), indent=2))
        return 0
    print(banner(client))
    if run is not None:
        print(f"model: {run.model}; {len(run.findings)} finding(s) given to the model as context")
    print()
    print(ask_command.render_text(answer))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.command == "explain":
        return _explain(args)
    if args.command == "ask":
        return _ask(args)
    print(f"oscal-validate: {args.command} is not available yet", file=sys.stderr)
    return 2
