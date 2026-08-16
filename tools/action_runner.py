"""Entry point for the composite GitHub Action in ``action.yml``.

The CLI is the gate. This script is only the part GitHub needs that the CLI
does not provide: expanding one ``path`` input into a set of documents,
turning each report into workflow annotations, and collapsing several per-file
exit codes into one. It re-implements no rule and no severity, and it reads
its counts out of the CLI's own ``--format json`` summary rather than deciding
anything itself.

The exit codes it returns are deliberately the CLI's own:

- 0: nothing at or above the requested threshold.
- 1: at least one finding at or above it.
- 2: a document could not be read or parsed, or the inputs were unusable.

Two deliberate refusals to pass silently: a ``path`` that matches no file at
all exits 2, because a gate that validated nothing is not a gate that passed;
and an unreadable document exits 2 even when every other document is clean.

``fail-on`` is the one thing the CLI has no flag for. ``oscal-validate`` gates
on ERROR and only ERROR, so a stricter threshold is applied here, from the
published summary counts. UNVERIFIABLE is excluded at every threshold, because
it marks what the supplied documents cannot settle and is never a pass.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

MODULE = "oscal_validate"
TOOL = "oscal-validate"

#: The tool's severities, in the order it reports them.
SEVERITIES = ("ERROR", "WARNING", "INFO", "UNVERIFIABLE")

#: What each ``fail-on`` setting gates on. UNVERIFIABLE is in none of them.
GATED: dict[str, tuple[str, ...]] = {
    "error": ("ERROR",),
    "warning": ("ERROR", "WARNING"),
    "info": ("ERROR", "WARNING", "INFO"),
}

#: Severity to GitHub annotation level. GitHub has three; the tool has four.
LEVELS = {"ERROR": "error", "WARNING": "warning", "INFO": "notice", "UNVERIFIABLE": "notice"}

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

GLOB_CHARACTERS = "*?["


def escape(text: str) -> str:
    """Escape a workflow-command message, per GitHub's own escaping rules."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(text: str) -> str:
    """Escape a workflow-command property value, which also eats ``:`` and ``,``."""
    return escape(text).replace(":", "%3A").replace(",", "%2C")


def annotate(level: str, message: str, *, file: str = "", title: str = "") -> None:
    properties = [
        f"{key}={escape_property(value)}"
        for key, value in (("file", file), ("title", title))
        if value
    ]
    joined = " " + ",".join(properties) if properties else ""
    print(f"::{level}{joined}::{escape(message)}")


def discover(raw: str) -> list[Path]:
    """Expand the ``path`` input into the documents to validate.

    A directory is searched recursively for ``*.json``. A glob is expanded.
    Anything else is handed to the CLI as written, so a path that does not
    exist is reported by the CLI, in the CLI's words, as exit code 2.
    """
    target = Path(raw)
    if target.is_dir():
        return sorted(path for path in target.rglob("*.json") if path.is_file())
    if any(character in raw for character in GLOB_CHARACTERS):
        matches = (Path(match) for match in glob.glob(raw, recursive=True))
        return sorted(match for match in matches if match.is_file())
    return [target]


def run_cli(document: Path, resolve: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run the CLI over one document, as a child process of this interpreter."""
    command = [sys.executable, "-m", MODULE, str(document), "--format", "json"]
    for extra in resolve:
        command += ["--resolve", extra]
    # S603 flags untrusted input reaching a subprocess. The action's inputs do
    # reach it, and that is the point: they are argv entries in a list, with
    # no shell to interpret them, so a caller controls what is validated and
    # never what is executed.
    return subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603


def report_findings(document: Path, findings: list[dict[str, str]]) -> None:
    for finding in findings:
        severity = str(finding["severity"])
        where = f"{finding['location']}: {finding['property']} = {finding['value']}"
        annotate(
            LEVELS.get(severity, "notice"),
            f"{where}. {finding['message']}",
            file=str(document),
            title=f"{finding['code']} ({severity})",
        )


def validate_one(document: Path, resolve: Sequence[str], totals: dict[str, int]) -> bool:
    """Validate one document and fold its counts into ``totals``.

    Returns False when the document could not be read, which is a failure of
    the run and not a finding about the document.
    """
    completed = run_cli(document, resolve)
    if completed.returncode not in (EXIT_CLEAN, EXIT_FINDINGS):
        detail = completed.stderr.strip() or f"{TOOL} exited {completed.returncode}"
        annotate("error", detail, file=str(document))
        return False
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        annotate("error", f"{TOOL} produced output this action could not read", file=str(document))
        return False

    report_findings(document, report["findings"])
    summary = report["summary"]
    for severity in SEVERITIES:
        totals[severity] += int(summary.get(severity, 0))
    counted = ", ".join(f"{summary.get(s, 0)} {s}" for s in SEVERITIES)
    print(f"{document} ({report['document']['model']}): {counted}")
    return True


def write_outputs(values: dict[str, int]) -> None:
    destination = os.environ.get("GITHUB_OUTPUT")
    if not destination:
        return
    with open(destination, "a", encoding="utf-8") as handle:
        for name, value in values.items():
            handle.write(f"{name}={value}\n")


def main() -> int:
    fail_on = (os.environ.get("OSCAL_FAIL_ON") or "error").strip().lower()
    if fail_on not in GATED:
        annotate("error", f"fail-on must be one of {', '.join(GATED)}, not {fail_on!r}")
        return EXIT_USAGE

    raw = (os.environ.get("OSCAL_PATH") or "").strip()
    if not raw:
        annotate("error", "path is required, and was empty")
        return EXIT_USAGE

    documents = discover(raw)
    if not documents:
        annotate(
            "error", f"path {raw!r} matched no file. Nothing was validated, which is not a pass."
        )
        return EXIT_USAGE

    resolve = (os.environ.get("OSCAL_RESOLVE") or "").split()
    totals = dict.fromkeys(SEVERITIES, 0)
    unreadable = sum(not validate_one(document, resolve, totals) for document in documents)

    write_outputs(
        {
            "error-count": totals["ERROR"],
            "warning-count": totals["WARNING"],
            "info-count": totals["INFO"],
            "unverifiable-count": totals["UNVERIFIABLE"],
            "files-validated": len(documents) - unreadable,
        }
    )
    print(
        f"{len(documents) - unreadable} of {len(documents)} document(s) validated: "
        + ", ".join(f"{totals[severity]} {severity}" for severity in SEVERITIES)
    )

    if unreadable:
        annotate("error", f"{unreadable} document(s) could not be read or parsed")
        return EXIT_USAGE
    gating = sum(totals[severity] for severity in GATED[fail_on])
    if gating:
        annotate(
            "error", f"{gating} finding(s) at or above {fail_on.upper()}, and fail-on is {fail_on}"
        )
        return EXIT_FINDINGS
    return EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
