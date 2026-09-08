"""``--format html``: one self-contained page, for the people who sign packages.

The reader this exists for is an ISSO or an assessor who does not run a CLI and
whose evidence of review is a file attached to a package. Until now the only
way to hand them findings was a pasted terminal dump, which loses the citation
links and cannot be searched.

Five properties are deliberate, and each of them is checked rather than
asserted:

**Self-contained.** One file. No script, no external stylesheet, no font, no
image, no `<link>`, no `src` of any kind. It opens with the network off and
requests nothing. The only external URLs are the citation hyperlinks a reader
may follow on purpose.

**Deterministic.** No timestamp, no run id, nothing that moves between two runs
over the same inputs. The provenance footer names the tool version, the OSCAL
release, the documents that were read and the SHA-256 of every vendored file
this run opened -- computed from the bytes, the way ``snapshot.py`` does it.

**Nothing suppressed.** Every finding the text report prints is on the page,
under the fix order :mod:`oscal_validate.fixorder` computes -- the same order
``walkthrough`` uses, from the same module, so the two cannot place a finding
differently. UNVERIFIABLE keeps its own section and is never folded into a
pass, and the summary states the count on the page rather than in a footnote.
A finding a ``--baseline`` acknowledged is on the page like any other, at its
own severity, in the same group, with the reason and the date beside it -- and
the summary's gating column says how many ERRORs are not gating rather than
answering "yes" for all of them. This page is the surface a person signs off
from, so an acknowledgement it did not show would be the machine-readable
report and the human-readable one disagreeing about the same run.

**Accessible, mechanically.** One ``h1``; heading levels that never skip;
``lang="en"``; a skip link that names an id that exists; a table per group with
a caption, ``th scope="col"`` headers and ``th scope="row"`` severity cells; and
severity carried by the word, never by colour. ``tests/test_html_report.py``
parses the output and checks each of those, and seeds a heading-order defect to
prove the parser can fail.

**Escaped.** Every value from the document goes through :func:`html.escape`
with quoting on. OSCAL documents are untrusted input; a report that rendered
one into markup would be a vulnerability in the tool that exists to read
untrusted files.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .findings import SEVERITY_ORDER, Finding, acknowledged_count, counts, stale_count
from .fixorder import UNSETTLED_TIER, CodeGroup, group_by_code
from .rules import OSCAL_RELEASE
from .snapshot import ALGORITHM, digests

#: The columns of every findings table, in order. One list, used to write the
#: header cells and to write each row, so a column cannot be added to the
#: header and left with no cells under it.
COLUMNS = ("Severity", "Location", "Property", "Value", "Message", "Rule")

STYLE = """
:root { color-scheme: light; }
body { margin: 0 auto; max-width: 60rem; padding: 1rem;
       font: 1rem/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
       color: #111; background: #fff; }
a { color: #0b3d91; }
a.skip-link { position: absolute; left: -100rem; }
a.skip-link:focus { position: static; display: inline-block; padding: 0.5rem; }
h1 { font-size: 1.75rem; }
h2 { font-size: 1.3rem; margin-top: 2.5rem; border-bottom: 1px solid #767676;
     padding-bottom: 0.25rem; }
h3 { font-size: 1.05rem; margin-top: 2rem; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0 1.5rem; }
caption { text-align: left; font-weight: 700; padding-bottom: 0.4rem; }
th, td { border: 1px solid #767676; padding: 0.4rem 0.5rem; text-align: left;
         vertical-align: top; }
thead th { background: #ededed; }
td code, th code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                   font-size: 0.9em; overflow-wrap: anywhere; }
.why { color: #333; margin: 0.25rem 0 0.75rem; }
.note { border-left: 4px solid #767676; padding: 0.25rem 0 0.25rem 0.75rem; }
footer { margin-top: 3rem; border-top: 1px solid #767676; padding-top: 1rem;
         font-size: 0.9rem; }
"""

DISCLAIMER = (
    "Structural conformance is not evidence that a control is implemented. This report "
    "says whether a document is well formed and whether its references resolve. It says "
    "nothing about the system the document describes, and it is not an assessment."
)

UNSETTLED_NOTE = (
    "UNVERIFIABLE is neither a pass nor a failure. It marks a question the documents "
    "supplied could not settle, and it never gates an exit code. A run with no ERROR "
    "findings is not a run in which every published rule passed."
)


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _code(value: str) -> str:
    return f"<code>{_escape(value)}</code>"


def _anchor(index: int) -> str:
    return f"group-{index}"


def _rule_cell(finding: Finding) -> str:
    rule = finding.rule
    citation = _escape(rule.citation)
    if rule.url.startswith(("http://", "https://")):
        where = f'<a href="{_escape(rule.url)}">{_escape(rule.url)}</a>'
    else:
        where = _escape(rule.url)
    retrieved = (
        "no retrieval date: this source travels with the repository"
        if rule.retrieved == "-"
        else f"retrieved {_escape(rule.retrieved)}"
    )
    return f"{citation}<br>Source: {where} ({retrieved})"


def _acknowledgement_note(finding: Finding) -> str:
    """What a baseline said about this finding, or nothing at all.

    Written into the row rather than into a column of its own, so a run with
    no baseline produces the same table it always produced. An acknowledged
    finding keeps its severity cell: the word in that cell is what the
    document is, and the note beneath is what a team decided about it.
    """
    acknowledged = finding.acknowledged
    if acknowledged is None:
        return ""
    return (
        f'<p class="note">Acknowledged {_escape(acknowledged.acknowledged_on)} by the '
        f"baseline: {_escape(acknowledged.reason)} &mdash; still "
        f"{_escape(finding.severity.value)} and still counted in the summary above; it "
        "does not gate the exit code.</p>"
    )


def _message_cell(finding: Finding) -> str:
    message = _escape(finding.message)
    note = _acknowledgement_note(finding)
    if not finding.suggestions:
        return message + note
    items = "".join(
        f"<li>{_code(s.value)} &mdash; {_escape(s.difference)}</li>" for s in finding.suggestions
    )
    return (
        f"{message}<p>Also declared, and close to the value written "
        f"(this is not a claim about what was meant):</p><ul>{items}</ul>{note}"
    )


def _row(finding: Finding) -> str:
    cells = (
        f'<th scope="row">{_escape(finding.severity.value)}</th>',
        f"<td>{_code(finding.location)}</td>",
        f"<td>{_code(finding.prop)}</td>",
        f"<td>{_code(finding.value)}</td>",
        f"<td>{_message_cell(finding)}</td>",
        f"<td>{_rule_cell(finding)}</td>",
    )
    return "      <tr>" + "".join(cells) + "</tr>"


def _group_section(index: int, group: CodeGroup) -> list[str]:
    heading = (
        f"{index}. {_escape(group.tier)}: {_escape(group.finding_code)} "
        f"({_escape(group.severity)}, {len(group.findings)} finding(s))"
    )
    lines = [
        f'    <h3 id="{_anchor(index)}">{heading}</h3>',
        f'    <p class="why">Why here in the fix order: {_escape(group.why)}</p>',
        "    <table>",
        f"      <caption>{_escape(group.finding_code)} &mdash; "
        f"{len(group.findings)} finding(s)</caption>",
        "      <thead>",
        "        <tr>"
        + "".join(f'<th scope="col">{_escape(column)}</th>' for column in COLUMNS)
        + "</tr>",
        "      </thead>",
        "      <tbody>",
    ]
    lines.extend(_row(finding) for finding in group.findings)
    lines.extend(["      </tbody>", "    </table>"])
    return lines


def _gates_cell(severity: str, findings: Sequence[Finding]) -> str:
    """Whether findings at this severity gate the exit code, for this run.

    Derived from :attr:`Finding.gates` rather than restated as "ERROR gates":
    that sentence stopped being true the moment ``--baseline`` existed, and a
    summary that answered ``yes`` over acknowledged findings would tell a
    reviewer the run failed a gate it passes.
    """
    at_severity = [f for f in findings if f.severity.value == severity]
    if not any(f.gates for f in at_severity):
        acknowledged = sum(1 for f in at_severity if f.acknowledged is not None)
        if acknowledged:
            return f"no &mdash; all {acknowledged} acknowledged by the baseline"
        return "no"
    acknowledged = sum(1 for f in at_severity if f.acknowledged is not None)
    if not acknowledged:
        return "yes"
    return (
        f"yes for {sum(1 for f in at_severity if f.gates)}; "
        f"{acknowledged} acknowledged by the baseline and not gating"
    )


def _summary_table(findings: Sequence[Finding]) -> list[str]:
    totals = counts(list(findings))
    lines = [
        "    <table>",
        "      <caption>Findings by severity</caption>",
        '      <thead><tr><th scope="col">Severity</th><th scope="col">Findings</th>'
        '<th scope="col">Gates the exit code</th></tr></thead>',
        "      <tbody>",
    ]
    for severity in SEVERITY_ORDER:
        lines.append(
            f'        <tr><th scope="row">{_escape(severity.value)}</th>'
            f"<td>{totals[severity.value]}</td>"
            f"<td>{_gates_cell(severity.value, findings)}</td></tr>"
        )
    lines.extend(["      </tbody>", "    </table>"])
    return lines


def _contents(groups: Sequence[CodeGroup]) -> list[str]:
    lines = ["    <ol>"]
    for index, group in enumerate(groups, 1):
        lines.append(
            f'      <li><a href="#{_anchor(index)}">{_escape(group.tier)}: '
            f"{_escape(group.finding_code)}</a> &mdash; {len(group.findings)} finding(s)</li>"
        )
    lines.append("    </ol>")
    return lines


def _provenance(document: Path, resolve: Sequence[Path], model: str) -> list[str]:
    lines = [
        "  <footer>",
        '    <h2 id="provenance">What decided this report</h2>',
        "    <table>",
        "      <caption>The run</caption>",
        '      <thead><tr><th scope="col">Fact</th><th scope="col">Value</th></tr></thead>',
        "      <tbody>",
        f'        <tr><th scope="row">Tool</th><td>oscal-validate {_escape(__version__)}</td></tr>',
        f'        <tr><th scope="row">OSCAL release judged against</th>'
        f"<td>{_escape(OSCAL_RELEASE)}</td></tr>",
        f'        <tr><th scope="row">Document</th><td>{_code(str(document))}</td></tr>',
        f'        <tr><th scope="row">Model at the document root</th>'
        f"<td>{_escape(model)}</td></tr>",
        f'        <tr><th scope="row">Supplied with --resolve</th>'
        f"<td>{_resolve_cell(resolve)}</td></tr>",
        "      </tbody>",
        "    </table>",
        "    <table>",
        "      <caption>Vendored files this run read, and the "
        f"{_escape(ALGORITHM)} of their bytes</caption>",
        '      <thead><tr><th scope="col">File</th>'
        f'<th scope="col">{_escape(ALGORITHM)}</th></tr></thead>',
        "      <tbody>",
    ]
    for relpath, digest in sorted(digests().items()):
        lines.append(
            f'        <tr><th scope="row">{_code(relpath)}</th><td>{_code(digest)}</td></tr>'
        )
    lines.extend(
        [
            "      </tbody>",
            "    </table>",
            "    <p>This page carries no timestamp. Two runs over the same inputs "
            "produce the same bytes, so a difference between two reports is a "
            "difference in what was read.</p>",
            "  </footer>",
        ]
    )
    return lines


def _resolve_cell(resolve: Sequence[Path]) -> str:
    if not resolve:
        return "nothing (no --resolve was given)"
    return "<br>".join(_code(str(path)) for path in resolve)


def _baseline_note(findings: Sequence[Finding], baseline: str) -> list[str]:
    """The paragraph a run given a ``--baseline`` carries, or no paragraph.

    Absent means no baseline was given, which is not the same as a baseline
    that acknowledged nothing: a run that was never given one makes no claim
    either way. Both counts come off the findings on the page, so this
    sentence cannot describe an acknowledgement the page does not show.
    """
    if not baseline:
        return []
    acknowledged = acknowledged_count(list(findings))
    stale = stale_count(list(findings))
    return [
        f'    <p class="note">Baseline: {_code(baseline)}. {acknowledged} finding(s) '
        f"acknowledged and not gating the exit code, {stale} entry(ies) that matched "
        "nothing in this run. Acknowledged findings are still on this page, still carry "
        "their own severity and are still counted above.</p>"
    ]


def render_findings_html(
    findings: list[Finding],
    version: str,
    model: str,
    document: Path,
    resolve: Sequence[Path] = (),
    baseline: str = "",
) -> str:
    """The whole page, as one string. ``version`` is accepted for symmetry with
    the other renderers and is not written into the page: the provenance table
    prints the package's own version, which is the one that produced it.

    ``baseline`` is the path a ``--baseline`` file was read from, or ``""``
    when none was, exactly as in the JSON and text renderers."""
    groups = group_by_code(findings)
    unsettled = sum(len(g.findings) for g in groups if g.tier == UNSETTLED_TIER)
    title = f"oscal-validate report: {document.name}"
    lines = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_escape(title)}</title>",
        f"<style>{STYLE}</style>",
        "</head>",
        "<body>",
        '  <a class="skip-link" href="#findings">Skip to the findings</a>',
        f"  <h1>{_escape(title)}</h1>",
        f'  <p class="note">{_escape(DISCLAIMER)}</p>',
        "  <section>",
        '    <h2 id="summary">Summary</h2>',
    ]
    lines.extend(_summary_table(findings))
    lines.append(
        f'    <p class="note">{_escape(UNSETTLED_NOTE)} This run reported {unsettled} '
        "UNVERIFIABLE finding(s).</p>"
    )
    lines.extend(_baseline_note(findings, baseline))
    lines.append("  </section>")
    lines.append("  <section>")
    lines.append('    <h2 id="findings">Findings, in fix order</h2>')
    if not groups:
        lines.append(
            "    <p>This run produced no findings at all. That is not the same as a "
            "document that passed every published rule; see the provenance below for "
            "what was read.</p>"
        )
    else:
        lines.append(
            "    <p>Groups are ordered by the structural dependency between them, not by "
            "severity: an unsupplied import comes before the references it leaves "
            "unsettled, and identifiers come before the references that name them.</p>"
        )
        lines.extend(_contents(groups))
        for index, group in enumerate(groups, 1):
            lines.extend(_group_section(index, group))
    lines.append("  </section>")
    lines.extend(_provenance(document, resolve, model))
    lines.extend(["</body>", "</html>", ""])
    return "\n".join(lines)
