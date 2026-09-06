"""One version, stated in four places, held together here.

`tests/test_cli.py::test_the_version_the_tool_reports_is_the_version_it_is`
exists because two of those places drifted: 0.2.0 shipped with the package
still reporting 0.1.0, so a stored report named the wrong release of the rules
that produced it. That test pins `oscal_validate.__version__` to
`pyproject.toml` and nothing else.

`CITATION.cff` states the version too, and states a release date beside it, and
was pinned to nothing at all. It is the file a reader cites this tool by, so a
version there that no longer matches the package is a citation to something
that was never built. This file closes that gap and adds the changelog: a
version the package reports and the changelog has never heard of is a release
with no record of what changed in it.

What this cannot check is whether a version was ever tagged. The suite runs
offline by construction (`tests/test_offline_guarantee.py`), and a clone has no
guarantee of carrying the repository's tags, so a test asserting a tag exists
would be measuring the checkout rather than the release. That gap is named in
`docs/ROADMAP.md` and in the README's Release & Versioning row instead of being
half-checked here.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from oscal_validate import __version__

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CITATION = ROOT / "CITATION.cff"
CHANGELOG = ROOT / "CHANGELOG.md"

#: ``version: "0.3.0"`` at the top level of the citation file. Matched rather
#: than parsed as YAML because the project has no runtime dependencies and no
#: YAML parser in the dev toolchain either; the field is one line and this
#: fails loudly if it stops being one.
CITATION_VERSION = re.compile(r'^version:\s*"?([^"\s]+)"?\s*$', re.MULTILINE)


def _manifest_version() -> str:
    manifest = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = manifest["project"]["version"]
    assert isinstance(version, str)
    return version


def test_the_citation_names_the_version_the_package_is() -> None:
    """A citation to a version the package never reported is a citation to nothing."""
    matches = CITATION_VERSION.findall(CITATION.read_text(encoding="utf-8"))
    assert len(matches) == 1, f"expected one top-level version: field, found {matches}"
    assert matches[0] == _manifest_version()
    assert matches[0] == __version__


def test_the_version_the_package_reports_has_a_changelog_section() -> None:
    """A version with no changelog entry is a release with no record of its changes.

    Keep a Changelog's heading form, so this is the same string a reader
    follows the ``## [Unreleased]`` section down to.
    """
    changelog = CHANGELOG.read_text(encoding="utf-8")
    heading = f"## [{__version__}] - "
    assert heading in changelog, f"CHANGELOG.md has no {heading!r} section"
