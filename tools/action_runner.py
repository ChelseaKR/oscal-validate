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

``sarif-file`` is the second: the CLI renders SARIF for one document, and a
code-scanning upload wants one file for the whole set. The merge itself is
:func:`oscal_validate.sarif.merge_logs`, imported rather than reimplemented,
because merging rules re-decides a rule's ``helpUri`` and that is a rendering
decision. What is decided *here* is when the file may be written at all, and
the answer is: only when every document produced a SARIF run whose result
count equals its own JSON summary. That is not caution for its own sake.
``upload-sarif`` treats an upload as the complete picture and resolves any
alert missing from it, so a SARIF file that lost a document's findings does
not merely under-report -- it closes real alerts as fixed. A partial file is
never written; the run fails instead.
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

#: The major version of ``report.schema.json`` this script knows how to read.
#: A report declaring a different major fails the run rather than being read
#: on a guess; see :func:`describe_unreadable`.
SUPPORTED_REPORT_SCHEMA_MAJOR = "1"

#: What each ``fail-on`` setting gates on. UNVERIFIABLE is in none of them.
GATED: dict[str, tuple[str, ...]] = {
    "error": ("ERROR",),
    "warning": ("ERROR", "WARNING"),
    "info": ("ERROR", "WARNING", "INFO"),
}

#: Severity to GitHub annotation level. GitHub has three; the tool has four.
LEVELS = {"ERROR": "error", "WARNING": "warning", "INFO": "notice", "UNVERIFIABLE": "notice"}

#: Where a severity this script does not know goes, if one ever reaches
#: :func:`report_findings`. It should not: :func:`describe_unreadable` refuses
#: such a report before anything is annotated. The default is ``error`` rather
#: than ``notice`` because the two directions are not symmetric -- an unknown
#: severity rendered as the mildest level GitHub has is an unread finding
#: wearing the appearance of a reviewed one, and `docs/API.md` says in terms
#: that a consumer "must not treat an unknown severity as a pass".
UNKNOWN_SEVERITY_LEVEL = "error"

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


def run_cli(
    document: Path, resolve: Sequence[str], report_format: str = "json"
) -> subprocess.CompletedProcess[str]:
    """Run the CLI over one document, as a child process of this interpreter."""
    command = [sys.executable, "-m", MODULE, str(document), "--format", report_format]
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
            LEVELS.get(severity, UNKNOWN_SEVERITY_LEVEL),
            f"{where}. {finding['message']}",
            file=str(document),
            title=f"{finding['code']} ({severity})",
        )


def describe_unreadable(report: object) -> str | None:
    """Why this report cannot be gated on, or ``None`` when it can.

    This exists because the previous reading was ``summary.get(severity, 0)``:
    a summary that had lost a key -- renamed, or written by a future version
    of the report -- counted as zero findings of that severity, and the gate
    passed. That is an absence published as a measurement, which is the
    defect this tool exists to report. A count that is not there is not a
    count of none, so a report missing any part of the contract fails the run
    (exit 2) instead of being read as clean.

    The same rule, said the other way round: **a count this script does not
    know how to gate on is not a count of zero either.** ``docs/API.md`` allows
    ``Severity`` to gain a member within a major version, and requires that a
    consumer "must not treat an unknown severity as a pass". This script did
    exactly that. ``validate_one`` folds only the four severities in
    :data:`SEVERITIES` into ``totals``, so a fifth would have been gated on by
    no ``fail-on`` threshold and the run would have exited 0; and
    ``report_findings`` mapped it through ``LEVELS.get(severity, "notice")``,
    the mildest level GitHub has, for a severity that might be graver than
    ERROR. Adding one is a minor bump, so both were reachable without any
    change this script would otherwise have noticed. A report carrying a
    severity this script does not know now fails the run instead.

    The check is on the shape the action actually reads, not the whole schema:
    the schema is the published contract and lives in the package, but this
    script must stay dependency-free and must not fail a run over a key it
    never looks at.
    """
    if not isinstance(report, dict):
        return "the report is not a JSON object"
    declared = report.get("report_schema_version")
    if not isinstance(declared, str):
        return "report_schema_version is missing"
    major = declared.split(".")[0]
    if major != SUPPORTED_REPORT_SCHEMA_MAJOR:
        return (
            f"report_schema_version is {declared}, and this action reads "
            f"{SUPPORTED_REPORT_SCHEMA_MAJOR}.x"
        )
    findings = report.get("findings")
    if not isinstance(findings, list):
        return "findings is missing or is not a list"
    unknown = sorted(
        {
            str(f.get("severity"))
            for f in findings
            if isinstance(f, dict) and f.get("severity") not in SEVERITIES
        }
    )
    if unknown:
        return (
            f"a finding carries severity {', '.join(unknown)}, which this action does not "
            f"know how to gate on. It is not counted as none"
        )
    document = report.get("document")
    if not isinstance(document, dict) or not isinstance(document.get("model"), str):
        return "document.model is missing"
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return "summary is missing"
    absent = [severity for severity in SEVERITIES if not isinstance(summary.get(severity), int)]
    if absent:
        return f"summary has no integer count for {', '.join(absent)}"
    extra = sorted(str(key) for key in summary if key not in SEVERITIES)
    if extra:
        # Not pedantry about an unexpected key. `validate_one` folds only the
        # four it knows into `totals`, so a count under any other name is a
        # population of findings that no `fail-on` threshold can reach, and
        # the run would exit 0 having silently declined to gate on it.
        return (
            f"summary carries a count for {', '.join(extra)}, which this action does not "
            f"know how to gate on. It is not counted as none"
        )
    return None


def describe_unusable_sarif(log: object, expected_results: int) -> str | None:
    """Why this SARIF log cannot go into the uploaded file, or ``None``.

    The result count is checked against the JSON summary the same run
    published, because those are two renderings of one list of findings and
    they cannot legitimately disagree. If they do, something dropped findings
    between them, and the smaller number is the one that would be uploaded --
    an absence that reads as a clean file.
    """
    if not isinstance(log, dict):
        return "the SARIF log is not a JSON object"
    runs = log.get("runs")
    if not isinstance(runs, list) or len(runs) != 1 or not isinstance(runs[0], dict):
        return "the SARIF log does not carry exactly one run"
    results = runs[0].get("results")
    if not isinstance(results, list):
        return "the SARIF run has no results array"
    if len(results) != expected_results:
        return (
            f"the SARIF run has {len(results)} result(s) and the JSON report "
            f"has {expected_results} finding(s)"
        )
    return None


def sarif_for(document: Path, resolve: Sequence[str], expected_results: int) -> object | None:
    """The SARIF log for one document, or ``None`` after saying what went wrong."""
    completed = run_cli(document, resolve, "sarif")
    if completed.returncode not in (EXIT_CLEAN, EXIT_FINDINGS):
        detail = completed.stderr.strip() or f"{TOOL} exited {completed.returncode}"
        annotate("error", f"SARIF output failed: {detail}", file=str(document))
        return None
    try:
        log: object = json.loads(completed.stdout)
    except json.JSONDecodeError:
        annotate("error", f"{TOOL} produced SARIF this action could not parse", file=str(document))
        return None
    unusable = describe_unusable_sarif(log, expected_results)
    if unusable is not None:
        annotate(
            "error",
            f"{TOOL} produced SARIF that cannot be uploaded: {unusable}",
            file=str(document),
        )
        return None
    return log


def validate_one(
    document: Path,
    resolve: Sequence[str],
    totals: dict[str, int],
    sarif_logs: list[object] | None = None,
) -> bool:
    """Validate one document and fold its counts into ``totals``.

    Returns False when the document could not be read, which is a failure of
    the run and not a finding about the document. When ``sarif_logs`` is
    given, the document's SARIF log is appended to it, and a document whose
    SARIF could not be produced or does not agree with its own JSON report is
    a failure too -- see the module docstring for why a partial SARIF file is
    worse than none.
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

    unreadable = describe_unreadable(report)
    if unreadable is not None:
        annotate(
            "error",
            f"{TOOL} produced a report this action could not read: {unreadable}",
            file=str(document),
        )
        return False

    report_findings(document, report["findings"])
    summary = report["summary"]

    if sarif_logs is not None:
        log = sarif_for(document, resolve, sum(int(summary[s]) for s in SEVERITIES))
        if log is None:
            return False
        sarif_logs.append(log)

    for severity in SEVERITIES:
        totals[severity] += int(summary[severity])
    counted = ", ".join(f"{summary[s]} {s}" for s in SEVERITIES)
    print(f"{document} ({report['document']['model']}): {counted}")
    return True


def write_sarif(destination: Path, logs: list[object]) -> bool:
    """Merge the per-document logs into one file, or say why nothing was written."""
    # Imported here, not at module scope, for the same reason the counts come
    # from the CLI: the merge is the package's own rendering decision and is
    # not reimplemented. It is deferred so that the rest of this script keeps
    # running against a CLI it only ever reaches by subprocess.
    from oscal_validate.sarif import merge_logs  # noqa: PLC0415

    try:
        merged = merge_logs(logs)
    except (ValueError, KeyError, TypeError) as error:
        annotate("error", f"the SARIF logs could not be merged into one file: {error}")
        return False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(merged + "\n", encoding="utf-8")
    except OSError as error:
        annotate("error", f"the SARIF file could not be written: {error}")
        return False
    print(f"{destination}: {len(logs)} document(s) merged into one SARIF run")
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
    sarif_file = (os.environ.get("OSCAL_SARIF_FILE") or "").strip()
    sarif_logs: list[object] | None = [] if sarif_file else None
    totals = dict.fromkeys(SEVERITIES, 0)
    unreadable = sum(
        not validate_one(document, resolve, totals, sarif_logs) for document in documents
    )

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
        if sarif_file:
            annotate(
                "error",
                f"no SARIF was written to {sarif_file}: {unreadable} document(s) are missing "
                "from it, and an upload missing findings resolves the alerts it omits",
            )
        annotate("error", f"{unreadable} document(s) could not be read or parsed")
        return EXIT_USAGE
    if sarif_logs is not None and not write_sarif(Path(sarif_file), sarif_logs):
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
