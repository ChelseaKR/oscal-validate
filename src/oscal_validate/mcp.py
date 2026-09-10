"""A read-only, offline MCP server over this validator.

ADR-0005 put the model at the edges and kept the validator the only source of
findings. This is the same boundary approached from the other side: instead of
this tool calling a model, a model's host calls this tool, and what it gets
back is the validator's own report rather than a model's account of one. The
``validate`` tool returns exactly the bytes ``--format json`` writes, and
``tests/test_mcp.py`` compares the two.

Four tools, and nothing else:

``validate``   a document path plus optional resolve paths, returning the JSON
               report and the exit code that run would have produced.
``rule``       the citation trail for one constraint identifier or finding
               code, the same answer ``oscal-validate rule --format json``
               prints.
``coverage``   which of NIST's published constraints this tool evaluates, and
               the reason for every one it does not.
``limits``     what a clean run does not mean, in the README's own words.

**Read-only and offline is the load-bearing half of this module.** It speaks
JSON-RPC 2.0 over stdio using the standard library alone. It takes no
dependency -- not an MCP SDK, not a transport library -- so
``pyproject.toml``'s ``dependencies = []`` is untouched and the no-network
claim stays mechanically checkable by the same source scan that has always
checked it (``tests/test_offline_guarantee.py``). It opens no socket, writes
no file, and imports no module under ``src/oscal_validate/ai/``; a request
that would need any of those is refused with the reason rather than answered
approximately.

**Every path is checked against a root before it is opened.** ``--root``
defaults to the working directory the server was launched in, because a
server with no root is a file-reading primitive for whatever is driving the
assistant, and a default of "anywhere" is not a default anyone chose.

**A refusal is an answer.** An unknown tool, a path outside the root, an
unreadable document, an identifier that names no rule: each comes back as a
result saying what was refused and why, never as an empty findings list.
An empty findings list is what a clean document looks like, and the one thing
this project will not do is publish an absence as a measurement.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TextIO

from . import __version__
from .document import DocumentError
from .findings import exit_code, render_findings_json
from .limits import read_limits
from .metaschema import Constraint, load_metaschema
from .rule import COVERAGE_DOC, code_answer, constraint_answer
from .rules import OSCAL_RELEASE, RETRIEVED
from .schema import SchemaError
from .validator import build_session, validate

#: The MCP revision this server speaks. Written down rather than negotiated
#: from a library, because there is no library: a version this server does not
#: implement is better refused by a client than guessed at here.
PROTOCOL_VERSION = "2024-11-05"

#: Reported to every client in the ``initialize`` response. The version is the
#: package's own, which ``tests/test_cli.py`` pins to ``pyproject.toml``. It is
#: not read from installed distribution metadata: the GitHub Action runs this
#: package straight off ``PYTHONPATH`` with nothing installed, and a lookup
#: that failed there would report a version no release has.
SERVER_INFO = {"name": "io.github.chelseakr/oscal-validate", "version": __version__}


class OutsideRoot(ValueError):
    """A path the server was asked to read is not under its root."""


# -- the tool surface --------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "validate",
        "description": (
            "Validate one OSCAL JSON document and return the report, byte for byte "
            "the same JSON the command line writes. Imports are resolved only "
            "against documents named in 'resolve'; nothing is ever fetched, so a "
            "reference this run could not settle comes back UNVERIFIABLE and is "
            "never a pass. Start here, then use 'rule' on any finding's code."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "the document to validate, under the server's root",
                },
                "resolve": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "further documents, or directories of them, to resolve imports "
                        "and references against"
                    ),
                },
                "locations": {
                    "type": "boolean",
                    "description": (
                        "add the 1-based line and column each finding's pointer points "
                        "at; null where this run has no position for a pointer"
                    ),
                },
                "suggest": {
                    "type": "boolean",
                    "description": (
                        "beside a reference that resolves to nothing, name declared "
                        "identifiers within a bounded edit distance of it. Never "
                        "offered for an UNVERIFIABLE reference, and never asserted to "
                        "be what was meant"
                    ),
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "rule",
        "description": (
            "The citation trail for one NIST constraint identifier (for example "
            "oscal-catalog-controls) or one finding code this tool emits (for "
            "example REFERENCE_UNVERIFIABLE): the declaring element verbatim from "
            "the vendored metaschema module, NIST's declared level, the target "
            "expression, and the specification section for that kind, each beside "
            "the SHA-256 of the bytes it was read from. Quote this rather than "
            "recalling what a rule says."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"identifier": {"type": "string"}},
            "required": ["identifier"],
        },
    },
    {
        "name": "coverage",
        "description": (
            "Which of NIST's published constraints this tool evaluates and which it "
            "does not, with a specific reason for every one it does not, plus the "
            "evaluated constraints that read an index nothing builds and so can "
            "never reach a definite answer. Read this before characterizing a run "
            "with no findings: 'no findings' and 'every published constraint "
            "passed' are different claims and only the first is ever true here."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "description": (
                        "restrict to one constraint kind, such as is-unique or allowed-values"
                    ),
                },
                "evaluated": {
                    "type": "boolean",
                    "description": "restrict to evaluated (true) or skipped (false) constraints",
                },
            },
        },
    },
    {
        "name": "limits",
        "description": (
            "What this tool does not do, in the project's own published words. "
            "Structural conformance is not evidence that a control is implemented; "
            "this tool checks documents and does not assess systems. Read this "
            "before saying anything about what a report means."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]

#: Words that turn a request into a question about implementation, security or
#: authorization -- the judgments this tool refuses to make. They arrive only
#: as a tool *name*, because none of the four tools takes free text, so this is
#: the whole surface a question can reach.
#:
#: Every word here is one ``ai/guard.py`` treats as a judgment, and
#: ``tests/test_mcp.py`` proves it by handing each one to ``guard.is_judgment``
#: in a sentence. The list is duplicated rather than imported on purpose: this
#: module may not import that package (ADR-0005's boundary runs both ways, and
#: ``tests/test_offline_guarantee.py`` enforces it), so the two are held
#: together by a test instead of by an import. A word that stops being a
#: judgment there fails here.
#:
#: It is deliberately no *wider* than that guard's own vocabulary either.
#: ``security`` and ``assessment`` read like obvious additions and are not
#: here, because a word this server refuses and that guard would let through
#: is two boundaries where the project claims one. A name carrying such a word
#: is still refused -- there is no tool by that name -- it simply gets the
#: plain "unknown tool" answer rather than the boundary sentence.
JUDGMENT_VOCABULARY = frozenset(
    {
        "acceptable",
        "accreditation",
        "accredited",
        "adequate",
        "ato",
        "authorisation",
        "authorization",
        "authorized",
        "certification",
        "certified",
        "compliant",
        "effective",
        "implemented",
        "inadequate",
        "ineffective",
        "insecure",
        "insufficient",
        "noncompliant",
        "secure",
        "sufficient",
        "unacceptable",
        "unauthorized",
        "unimplemented",
        "unsafe",
        "unsecure",
    }
)

#: The sentence a judgment-shaped request is refused with. It states the
#: boundary rather than apologising for it, and it names the tool that answers
#: the question the caller can have answered.
BOUNDARY = (
    "this server reports structural conformance and makes no judgment about "
    "implementation, security or authorization. Structural conformance is not "
    "evidence that a control is implemented. Call 'limits' for what a clean run "
    "does not mean, and 'validate' for what this tool can actually say about a "
    "document."
)

_WORD = re.compile(r"[^a-z0-9]+")


def is_judgment_request(name: str) -> bool:
    """Whether a tool name is asking for a verdict this tool does not give.

    Matched on whole words of the name rather than on substrings: ``ato`` is
    inside ``validator`` and ``secure`` is inside ``insecurely``, and a
    substring scan over names is how a gate ends up refusing the wrong thing.
    A false positive here costs one extra sentence on a refusal the server was
    going to make anyway, because this is only ever consulted for a name that
    is not one of the four tools.
    """
    return any(word in JUDGMENT_VOCABULARY for word in _WORD.split(name.lower()) if word)


# -- results -----------------------------------------------------------------


def _text(payload: object) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}]}


def _refusal(reason: str, **detail: Any) -> dict[str, Any]:
    """Every refusal is an answer with a reason, never an empty result set."""
    return _text({"outcome": "refused", "reason": reason, **detail})


# -- the root ----------------------------------------------------------------


def within(root: Path, candidate: str) -> Path:
    """The path ``candidate`` names, or :class:`OutsideRoot` naming both.

    A relative path is resolved against the root rather than against the
    process's working directory, because the root is the world this server
    was given. ``resolve()`` follows symlinks before the comparison, so a link
    inside the root pointing out of it is refused rather than followed: the
    question is which bytes get read, not which name was typed.
    """
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise OutsideRoot(
            f"{candidate!r} resolves to {resolved}, which is outside this server's root "
            f"{root}. Restart the server with --root naming a directory that contains it, "
            "or ask for a path inside the root."
        )
    return resolved


# -- validate ----------------------------------------------------------------


def _flag(arguments: dict[str, Any], name: str) -> bool:
    return bool(arguments.get(name))


def _validate(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    path = arguments.get("path")
    if not isinstance(path, str) or not path.strip():
        return _refusal("validate needs 'path', the OSCAL JSON document to read", exit_code=2)
    supplied = arguments.get("resolve") or []
    if not isinstance(supplied, list) or any(not isinstance(p, str) for p in supplied):
        return _refusal("'resolve' must be a list of paths", exit_code=2)
    try:
        document = within(root, path)
        resolve = [within(root, p) for p in supplied]
    except OutsideRoot as exc:
        return _refusal(str(exc), exit_code=2)

    locations = _flag(arguments, "locations")
    try:
        session = build_session(
            document, resolve, suggest=_flag(arguments, "suggest"), locations=locations
        )
        findings = validate(session)
    except (DocumentError, SchemaError) as exc:
        # Exit-2 semantics, as the command line has them: a document that
        # could not be read has not been found clean, and a caller must be
        # able to tell that from a document with no findings in it.
        return _refusal(str(exc), exit_code=2, document=str(document))
    except RecursionError:
        return _refusal(
            f"{document} nests too deeply to read safely", exit_code=2, document=str(document)
        )

    report = render_findings_json(
        findings, __version__, session.corpus.primary.walked.model, locations=locations
    )
    return _text(
        {
            "outcome": "validated",
            "document": str(document),
            # The verdict the command line would return for this run, decided
            # by findings.exit_code so that the two front doors cannot come to
            # disagree about whether a document passed.
            "exit_code": exit_code(findings),
            "report": json.loads(report),
        }
    )


# -- rule --------------------------------------------------------------------


def _rule(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    del root  # reads only vendored package data
    identifier = arguments.get("identifier")
    if not isinstance(identifier, str) or not identifier.strip():
        return _refusal("rule needs 'identifier', a NIST constraint identifier or a finding code")
    answer = code_answer(identifier) or constraint_answer(identifier)
    if answer is None:
        return _refusal(
            f"no constraint and no finding code is named {identifier!r}",
            constraint_identifiers=COVERAGE_DOC,
            finding_codes="the README's finding-code table, or the 'coverage' tool",
        )
    return _text(answer.to_dict())


# -- coverage ----------------------------------------------------------------


def _constraint_row(constraint: Constraint) -> dict[str, Any]:
    row: dict[str, Any] = {
        "identifier": constraint.identifier or None,
        "kind": constraint.kind,
        "declared_on": constraint.context or None,
        "target": constraint.target or None,
        "evaluated": constraint.evaluated,
    }
    if constraint.evaluated:
        row["level"] = constraint.level
    else:
        row["not_evaluated_because"] = constraint.skipped
    return row


def _coverage(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    del root  # reads only vendored package data
    metaschema = load_metaschema()
    published = metaschema.constraints
    kind = arguments.get("kind")
    if kind is not None and not isinstance(kind, str):
        return _refusal("'kind' must be a constraint kind, as a string")
    wanted = arguments.get("evaluated")
    if wanted is not None and not isinstance(wanted, bool):
        return _refusal("'evaluated' must be true or false")

    matched = [
        c
        for c in published
        if (kind is None or c.kind == kind) and (wanted is None or c.evaluated is wanted)
    ]
    if kind is not None and not matched:
        return _refusal(
            f"no constraint of kind {kind!r} is published in the vendored release",
            kinds_published=sorted({c.kind for c in published}),
        )
    kinds = sorted({c.kind for c in published})
    return _text(
        {
            "oscal_release": OSCAL_RELEASE,
            "vendored_retrieved": RETRIEVED,
            "published": len(published),
            "evaluated": len(metaschema.evaluated()),
            # Both numbers on the line, always. A filtered answer that printed
            # only its own rows would read exactly like the whole table.
            "matched": len(matched),
            "filters": {"kind": kind, "evaluated": wanted},
            "by_kind": [
                {
                    "kind": name,
                    "published": sum(1 for c in published if c.kind == name),
                    "evaluated": sum(1 for c in published if c.kind == name and c.evaluated),
                }
                for name in kinds
            ],
            "constraints": [
                _constraint_row(c)
                for c in sorted(matched, key=lambda c: (c.kind, c.identifier, c.target))
            ],
            "reading_an_index_that_is_never_built": [
                {
                    "identifier": constraint.identifier,
                    "declared_on": constraint.context,
                    "reads_index": constraint.index_name,
                    "populated_by": populated_by,
                    "populated_by_is_evaluated": False,
                }
                for constraint, populated_by in metaschema.stranded_index_lookups()
            ],
            "note": (
                "A constraint listed as not evaluated is neither passed nor failed. A "
                "document this tool reports no findings for may still violate any of them. "
                "The constraints under reading_an_index_that_is_never_built are parsed and "
                "run and can never reach a definite answer, because the index constraint "
                "that would populate the index they read is itself not evaluated; "
                "references checked against them are reported UNVERIFIABLE."
            ),
            "document": COVERAGE_DOC,
        }
    )


# -- limits ------------------------------------------------------------------


def _limits(root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    del root, arguments
    published = read_limits()
    metaschema = load_metaschema()
    return _text(
        {
            "boundary": (
                "Structural conformance is not evidence that a control is implemented. "
                "This tool checks documents; it does not assess systems."
            ),
            "severities": {
                "ERROR": "the document violates a cited structural rule",
                "WARNING": (
                    "a cited signal that something is very likely wrong, where the rule is "
                    "not absolute or its enforcement by any authorizing body is not "
                    "documented"
                ),
                "INFO": "worth a human look; not a defect on its own",
                "UNVERIFIABLE": (
                    "the answer cannot be determined from the documents supplied. Never a "
                    "pass and never a fail"
                ),
            },
            "a_clean_run_means": (
                f"the {len(metaschema.evaluated())} of {len(metaschema.constraints)} "
                "published constraints this tool evaluates found nothing, over the "
                "documents that were supplied. It does not mean the other constraints "
                "passed, and it does not mean anything at all about whether a control is "
                "implemented."
            ),
            **published,
        }
    )


# -- dispatch ----------------------------------------------------------------

_Handler = Callable[[Path, dict[str, Any]], dict[str, Any]]

HANDLERS: dict[str, _Handler] = {
    "validate": _validate,
    "rule": _rule,
    "coverage": _coverage,
    "limits": _limits,
}


def call_tool(root: Path, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one tool call, refusing an unknown name rather than approximating."""
    handler = HANDLERS.get(name)
    if handler is None:
        if is_judgment_request(name):
            return _refusal(
                f"there is no tool {name!r}, and {BOUNDARY}",
                available_tools=sorted(HANDLERS),
            )
        return _refusal(f"unknown tool {name!r}", available_tools=sorted(HANDLERS))
    return handler(root, arguments)


def handle(root: Path, request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        result: dict[str, Any] = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = request.get("params")
        params = params if isinstance(params, dict) else {}
        arguments = params.get("arguments")
        result = call_tool(
            root,
            str(params.get("name") or ""),
            arguments if isinstance(arguments, dict) else {},
        )
    elif request_id is None:
        return None  # a notification this server does not act on
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"unknown method {method!r}"},
        }
    if request_id is None:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(code: int, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def _write(sink: TextIO, payload: dict[str, Any]) -> None:
    sink.write(json.dumps(payload) + "\n")
    sink.flush()


def serve(root: Path, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    """Read one JSON-RPC request per line and answer it.

    A bad request never kills the server: an unreadable line is a parse error
    and an exception inside a handler is an internal error, both reported to
    the client with the request's own id where there is one.
    """
    source = sys.stdin if stdin is None else stdin
    sink = sys.stdout if stdout is None else stdout
    for raw in source:
        line = raw.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            _write(sink, {"jsonrpc": "2.0", "id": None, "error": _error(-32700, "parse error")})
            continue
        try:
            response = handle(root, request if isinstance(request, dict) else {})
        except Exception as exc:  # a bad request must not kill the server
            identifier = request.get("id") if isinstance(request, dict) else None
            response = {
                "jsonrpc": "2.0",
                "id": identifier,
                "error": _error(-32603, f"{type(exc).__name__}: {exc}"),
            }
        if response is not None:
            _write(sink, response)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oscal-validate mcp",
        description=(
            "Serve this validator to an assistant over stdio, read-only and offline. "
            "Speaks JSON-RPC 2.0 (MCP " + PROTOCOL_VERSION + ") on stdin and stdout, "
            "and exposes four tools: validate, rule, coverage and limits. No tool "
            "fetches anything, writes anything, or calls a model; the findings a "
            "client gets are this validator's own, byte for byte."
        ),
        epilog=(
            "Every path a tool is given is resolved and checked against --root before "
            "it is opened, and a path outside it is refused with the reason."
        ),
    )
    parser.add_argument(
        "--root",
        default=".",
        metavar="DIR",
        help=(
            "the only directory whose documents this server will read (default: the "
            "working directory it was started in). Symbolic links are followed before "
            "the check, so a link out of the root is refused rather than traversed"
        ),
    )
    return parser


def main(argv: Sequence[str]) -> int:
    args = build_parser().parse_args(list(argv)[1:])
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"oscal-validate mcp: --root {args.root} is not a directory", file=sys.stderr)
        return 2
    return serve(root)
