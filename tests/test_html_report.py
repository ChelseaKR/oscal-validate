"""``--format html``: self-contained, deterministic, and mechanically accessible.

The accessibility checks below are the point of this file. A page nobody can
read is not a report, and "we were careful" is not a check -- so the output is
parsed with the standard library and held to seven structural rules, each of
which is *proved able to fail* by seeding the exact defect it exists to catch.
A checker that has never gone red is a gate that cannot fail, which is this
repository's own dominant defect wearing an accessibility gate's clothes.
"""

from __future__ import annotations

import html
import re
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, NoReturn

import pytest

from oscal_validate import Finding, Rule, Severity, validate_file
from oscal_validate import __version__ as tool_version
from oscal_validate.ai import walkthrough
from oscal_validate.ai.run import prepare
from oscal_validate.cli import main
from oscal_validate.fixorder import UNSETTLED_TIER, group_by_code
from oscal_validate.htmlreport import COLUMNS, render_findings_html
from oscal_validate.snapshot import digests
from oscal_validate.suggest import Suggestion

from .conftest import fixture_path

ROOT = Path(__file__).resolve().parent.parent

#: Elements that would make the page fetch something. A self-contained report
#: has none of them, and neither has any attribute that names a subresource.
FETCHING_ELEMENTS = ("script", "link", "iframe", "embed", "object", "img", "audio", "video")
SUBRESOURCE_ATTRIBUTES = ("src", "srcset", "data", "poster", "background")
CONTROLS = ("input", "select", "textarea")


@dataclass
class _Table:
    columns: int = 0
    caption: bool = False
    rows: list[int] = field(default_factory=list)
    in_row: bool = False
    current: int = 0


class Accessibility(HTMLParser):
    """Seven structural rules, checked over the rendered bytes.

    Deliberately not a full WCAG audit -- it cannot judge whether a sentence is
    comprehensible or whether a colour pair passes at the size it is rendered.
    It checks the things that are mechanical, and it says which rule failed.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []
        self.headings: list[int] = []
        self.ids: set[str] = set()
        self.labelled_controls: set[str] = set()
        self.control_ids: list[str] = []
        self.local_links: list[str] = []
        self.language = ""
        self._tables: list[_Table] = []

    # -- parsing ------------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: (value or "") for name, value in attrs}
        self._note_identity(tag, attributes)
        self._note_fetching(tag, attributes)
        self._note_structure(tag, attributes)
        self._note_table(tag, attributes)

    def _note_identity(self, tag: str, attributes: dict[str, str]) -> None:
        identifier = attributes.get("id", "")
        if identifier:
            if identifier in self.ids:
                self.problems.append(f"duplicate id: {identifier}")
            self.ids.add(identifier)
        if tag == "html":
            self.language = attributes.get("lang", "")
        if tag in CONTROLS:
            self.control_ids.append(identifier)

    def _note_fetching(self, tag: str, attributes: dict[str, str]) -> None:
        if tag in FETCHING_ELEMENTS:
            if tag == "img" and not attributes.get("alt", "").strip():
                self.problems.append("an img with no alt text")
            self.problems.append(f"a fetching element: <{tag}>")
        for attribute in SUBRESOURCE_ATTRIBUTES:
            if attribute in attributes:
                self.problems.append(f"<{tag}> names a subresource in {attribute}=")

    def _note_structure(self, tag: str, attributes: dict[str, str]) -> None:
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        elif tag == "a" and attributes.get("href", "").startswith("#"):
            self.local_links.append(attributes["href"][1:])
        elif tag == "label" and attributes.get("for", ""):
            self.labelled_controls.add(attributes["for"])

    def _note_table(self, tag: str, attributes: dict[str, str]) -> None:
        if tag == "table":
            self._tables.append(_Table())
        if not self._tables:
            return
        table = self._tables[-1]
        if tag == "caption":
            table.caption = True
        elif tag == "tr":
            table.in_row = True
            table.current = 0
        elif tag in ("th", "td"):
            table.current += 1
            if tag == "th" and attributes.get("scope", "") not in ("col", "row"):
                self.problems.append("a th with no scope")

    def handle_endtag(self, tag: str) -> None:
        if not self._tables:
            return
        table = self._tables[-1]
        if tag == "tr" and table.in_row:
            table.in_row = False
            if table.columns == 0:
                table.columns = table.current
            table.rows.append(table.current)
        elif tag == "table":
            self._finish(self._tables.pop())

    def _finish(self, table: _Table) -> None:
        if not table.caption:
            self.problems.append("a table with no caption")
        if not table.rows:
            self.problems.append("a table with no rows")
        for width in table.rows:
            if width != table.columns:
                self.problems.append(
                    f"a table row with {width} cell(s) under {table.columns} header(s)"
                )

    # -- the rules ----------------------------------------------------------

    def check(self) -> list[str]:
        problems = list(self.problems)
        if self.language != "en":
            problems.append(f"the document declares lang={self.language!r}")
        if self.headings.count(1) != 1:
            problems.append(f"{self.headings.count(1)} h1 elements; there must be exactly one")
        if self.headings and self.headings[0] != 1:
            problems.append("the first heading is not the h1")
        for previous, current in zip(self.headings, self.headings[1:], strict=False):
            if current > previous + 1:
                problems.append(f"heading level jumps from h{previous} to h{current}")
        for target in self.local_links:
            if target not in self.ids:
                problems.append(f"an in-page link to #{target}, which nothing declares")
        for identifier in self.control_ids:
            if identifier not in self.labelled_controls:
                problems.append(f"a form control with no label: id={identifier!r}")
        return problems


def _audit(markup: str) -> list[str]:
    parser = Accessibility()
    parser.feed(markup)
    parser.close()
    return parser.check()


class _Attributes(HTMLParser):
    """Every attribute name the parser sees, so an injected one can be named."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.names: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.names.update(name for name, _ in attrs)


def _attribute_names(markup: str) -> set[str]:
    parser = _Attributes()
    parser.feed(markup)
    parser.close()
    return parser.names


def _report(document: str, resolve: tuple[str, ...] = ()) -> str:
    paths = [fixture_path(name) for name in resolve]
    findings = validate_file(fixture_path(document), paths)
    return render_findings_html(findings, tool_version, "catalog", fixture_path(document), paths)


# -- the accessibility checker itself can fail --------------------------------


@pytest.mark.parametrize(
    ("name", "seed", "expected"),
    [
        ("heading order", ('<h2 id="summary">', '<h4 id="summary">'), "heading level jumps"),
        ("a second h1", ('<h2 id="summary">', '<h1 id="summary">'), "h1 elements"),
        ("language", ('<html lang="en">', "<html>"), "declares lang"),
        ("a dangling skip link", ('<h2 id="findings">', "<h2>"), "which nothing declares"),
        ("an unlabelled control", ("</body>", '<input id="q"></body>'), "no label"),
        ("an image with no alt", ("</body>", '<img src="x.png"></body>'), " img with no alt"),
        (
            "a caption that went missing",
            ("<caption>Findings by severity</caption>", ""),
            "no caption",
        ),
        (
            "a column with no cells under it",
            ('<th scope="col">Gates the exit code</th>', ""),
            "cell(s) under",
        ),
    ],
)
def test_the_accessibility_checker_catches_the_defect_it_exists_to_catch(
    name: str, seed: tuple[str, str], expected: str
) -> None:
    """Every rule is seeded once. A checker that has never gone red is not a
    check; the parametrisation is what makes each of these evidence."""
    markup = _report("broken_catalog.json")
    before, after = seed
    assert before in markup, f"{name}: the seed did not match, so this proves nothing"
    damaged = markup.replace(before, after, 1)
    assert damaged != markup, name
    problems = _audit(damaged)
    assert any(expected in problem for problem in problems), (name, problems)


# -- and the real page passes it ----------------------------------------------


@pytest.mark.parametrize(
    ("document", "resolve"),
    [
        ("broken_catalog.json", ()),
        ("clean_catalog.json", ()),
        ("clean_profile.json", ()),
        ("clean_profile.json", ("clean_catalog.json",)),
        ("nist_ssp_example.json", ()),
    ],
)
def test_every_rendered_report_passes_the_accessibility_checks(
    document: str, resolve: tuple[str, ...]
) -> None:
    assert _audit(_report(document, resolve)) == []


def test_a_report_with_no_findings_at_all_is_still_a_valid_page() -> None:
    markup = render_findings_html([], tool_version, "catalog", Path("empty.json"))
    assert _audit(markup) == []
    assert "no findings at all" in markup
    assert "not the same as a document that passed" in markup


# -- self-contained ------------------------------------------------------------


def test_the_page_fetches_nothing_and_carries_its_own_style() -> None:
    markup = _report("broken_catalog.json")
    assert "<style>" in markup
    for element in FETCHING_ELEMENTS:
        assert f"<{element}" not in markup, element
    assert "src=" not in markup
    # The only external URLs are citation hyperlinks, which a reader follows on
    # purpose. Nothing loads them.
    for match in re.findall(r'href="([^"]+)"', markup):
        assert match.startswith(("#", "https://", "README.md")), match


def test_rendering_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError("this code path must not open a socket")

    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)
    assert _audit(_report("broken_catalog.json")) == []


# -- nothing suppressed --------------------------------------------------------


def test_the_broken_fixture_shows_its_three_errors_each_with_a_citation() -> None:
    findings = validate_file(fixture_path("broken_catalog.json"))
    errors = [f for f in findings if f.severity is Severity.ERROR]
    assert len(errors) == 3, "the fixture changed; this test is about those three"
    markup = _report("broken_catalog.json")
    for finding in errors:
        assert html.escape(finding.location, quote=True) in markup
        assert html.escape(finding.rule.citation, quote=True) in markup
    # Split at the findings heading: the summary table carries an ERROR row of
    # its own, and counting over the whole page would silently accept two
    # findings plus the summary as three findings.
    _, listed = markup.split('<h2 id="findings">', 1)
    assert listed.count('<th scope="row">ERROR</th>') == 3
    assert markup.count('<th scope="row">ERROR</th>') == 4


def test_unverifiable_keeps_its_own_section_and_is_never_a_pass() -> None:
    markup = _report("clean_profile.json")
    assert UNSETTLED_TIER in markup
    assert "neither a pass nor a failure" in markup
    assert '<th scope="row">UNVERIFIABLE</th>' in markup
    assert "not a run in which every published rule passed" in markup


def test_every_finding_the_text_report_holds_is_on_the_page() -> None:
    findings = validate_file(fixture_path("nist_ssp_example.json"))
    markup = _report("nist_ssp_example.json")
    rows = markup.count('<tr><th scope="row">')
    # Four severity rows in the summary table, plus the provenance tables'
    # rows, plus one row per finding.
    provenance_rows = 5 + len(digests())
    assert rows == len(findings) + 4 + provenance_rows


def test_the_group_order_is_the_one_walkthrough_uses() -> None:
    """One fix order, from one module. If these ever differed, a reviewer's
    page and the narrative would place the same finding in different
    positions and neither would say so."""
    run = prepare(fixture_path("nist_ssp_example.json"))
    assert [g.code for g in walkthrough.group(run)] == [
        g.finding_code for g in group_by_code(run.findings)
    ]


# -- deterministic and escaped -------------------------------------------------


def _render_in_a_subprocess(seed: str) -> bytes:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "oscal_validate",
            str(fixture_path("broken_catalog.json")),
            "--format",
            "html",
        ],
        capture_output=True,
        check=False,
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": seed, "PYTHONPATH": str(ROOT / "src")},
    )
    assert result.returncode == 1, result.stderr
    return result.stdout


def test_two_runs_are_byte_identical_across_processes_and_hash_seeds() -> None:
    outputs = {_render_in_a_subprocess(seed) for seed in ("0", "1", "12345")}
    assert len(outputs) == 1
    assert b"<!DOCTYPE html>" in outputs.pop()


def test_the_page_carries_no_timestamp() -> None:
    markup = _report("broken_catalog.json")
    assert not re.search(r"\b20\d\d-\d\d-\d\dT", markup), "an ISO timestamp reached the page"
    assert "This page carries no timestamp" in markup


def test_the_provenance_footer_names_every_vendored_file_and_its_digest() -> None:
    markup = _report("clean_profile.json", ("clean_catalog.json",))
    for relpath, digest in digests().items():
        assert relpath in markup, relpath
        assert digest in markup, relpath
    assert "clean_catalog.json" in markup, "the --resolve set must be on the page"
    assert tool_version in markup


def test_a_value_that_looks_like_markup_is_escaped_not_rendered() -> None:
    """OSCAL documents are untrusted input. This is the injection test.

    The rule URL carries a double quote on purpose. It is the only value this
    renderer puts inside an attribute, so it is the only place where escaping
    with ``quote=False`` would still look correct in element text and let a
    value break out of the markup. A first version of this test used a URL with
    no quote in it and stayed green under exactly that mutation.
    """
    rule = Rule(
        citation='<img src=x onerror="alert(1)">',
        url='https://example.invalid/?a=1&b=2" onmouseover="alert(1)',
        retrieved="2026-01-01",
    )
    finding = Finding(
        code="REFERENCE_UNRESOLVED",
        severity=Severity.ERROR,
        location="/catalog/<script>alert(1)</script>",
        prop="href",
        value='"><script>alert(1)</script>',
        message="a message with <b>markup</b> & an ampersand",
        rule=rule,
    )
    markup = render_findings_html([finding], tool_version, "catalog", Path("x.json"))
    assert "<script>" not in markup
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in markup
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in markup
    # The attribute case: the quote in the URL must be escaped, so no attribute
    # named onmouseover can exist anywhere on the page.
    assert 'href="https://example.invalid/?a=1&amp;b=2&quot; onmouseover=&quot;alert(1)"' in markup
    assert _audit(markup) == []
    assert "onmouseover" not in _attribute_names(markup)


def test_a_suggestion_is_rendered_as_a_list_and_says_what_it_is_not() -> None:
    """``--suggest`` names identifiers that ARE declared. The page has to carry
    the disclaimer the text report carries, or the list reads as an answer."""
    finding = Finding(
        code="REFERENCE_UNRESOLVED",
        severity=Severity.ERROR,
        location="/catalog/groups/0/controls/0/links/0/href",
        prop="href",
        value="#ex-01",
        message="This names an OSCAL object by its identifier, and no such identifier "
        "is declared in the documents supplied.",
        rule=Rule(citation="c", url="https://example.invalid/", retrieved="2026-01-01"),
        suggestions=(Suggestion("ex-1", "zero-padding"), Suggestion("ex-2", "one character")),
    )
    markup = render_findings_html([finding], tool_version, "catalog", Path("x.json"))
    assert _audit(markup) == []
    assert "not a claim about what was meant" in markup
    # One <li> per suggestion, inside the finding's own cell. The contents list
    # at the top of the findings section carries one more, which is why this
    # counts the suggestion markup rather than the bare tag.
    assert markup.count("<li><code>ex-") == 2
    assert "zero-padding" in markup


def test_the_columns_are_written_once() -> None:
    """The header and the rows come from one list, so a column cannot be added
    to the header and left with no cells under it -- the failure the row-width
    rule above catches, kept impossible at the source as well."""
    assert len(COLUMNS) == 6
    markup = _report("broken_catalog.json")
    for column in COLUMNS:
        assert f'<th scope="col">{column}</th>' in markup


# -- the command ---------------------------------------------------------------


def test_the_cli_writes_the_page_and_keeps_the_exit_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([str(fixture_path("broken_catalog.json")), "--format", "html"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("<!DOCTYPE html>")
    assert out.endswith("</html>\n")
    assert _audit(out) == []


def test_a_clean_document_still_exits_zero_in_html(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([str(fixture_path("clean_catalog.json")), "--format", "html"]) == 0
    assert _audit(capsys.readouterr().out) == []
