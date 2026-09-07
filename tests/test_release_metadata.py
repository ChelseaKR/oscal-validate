"""One version, stated in several places, held to the tags that actually exist.

`tests/test_cli.py::test_the_version_the_tool_reports_is_the_version_it_is`
exists because two of those places drifted: 0.2.0 shipped with the package
still reporting 0.1.0, so a stored report named the wrong release of the rules
that produced it. That test pins `oscal_validate.__version__` to
`pyproject.toml` and nothing else.

This file used to pin `CITATION.cff` to `pyproject.toml` the same way, and that
pin is what produced the defect it was meant to prevent. `pyproject.toml`
declares the version *under development*; `CITATION.cff` states the version a
reader should cite and the date it was released. Chaining the second to the
first meant that bumping the manifest to 0.3.0 moved the citation file to
`version: "0.3.0"` and `date-released: "2026-09-02"` — a release date for a
release that was never cut. No `v0.3.0` tag exists; nothing was built,
published, or archived on 2026-09-02. The citation pointed at nothing.

So the rule here is reality, not agreement:

* `CITATION.cff` must name a version that was tagged, dated with that tag's own
  date. When no tag exists at all it may name no release date.
* The README's Status paragraph must name the declared version and every tag
  that exists, and say plainly when the declared version is not among them.
* The declared version must have a changelog section behind it.

An earlier revision of this file argued that a tag check "would be measuring
the checkout rather than the release", because a clone has no guarantee of
carrying tags. That is true and it is the reason the checks below refuse to
draw any conclusion from an empty tag list unless the checkout could have shown
one — `_why_tags_are_unreadable` — and the reason
`test_ci_fetches_the_tags_these_checks_read` exists, so that the one run these
gates have to pass is a run where the tags are there. An empty tag list read
from a shallow checkout is absence rendered as a value, which is the defect
class this repository reports on.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from oscal_validate import __version__

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CITATION = ROOT / "CITATION.cff"
CHANGELOG = ROOT / "CHANGELOG.md"
README = ROOT / "README.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

#: ``version: "0.2.0"`` at the top level of the citation file. Matched rather
#: than parsed as YAML because the project has no runtime dependencies and no
#: YAML parser in the dev toolchain either; the field is one line and this
#: fails loudly if it stops being one.
CITATION_VERSION = re.compile(r'^version:\s*"?([^"\s#]+)"?\s*$', re.MULTILINE)
CITATION_DATE = re.compile(r'^date-released:\s*"?(\d{4}-\d{2}-\d{2})"?\s*$', re.MULTILINE)

#: A release tag, with or without the ``v``. Anything else in ``refs/tags`` is
#: not a release and is not counted as one.
RELEASE_TAG = re.compile(r"^v?(\d+\.\d+\.\d+(?:[-+.].+)?)$")

#: The ``**Status:** ...`` paragraph, which is where a reader who reads nothing
#: else learns what has and has not been released.
README_STATUS = re.compile(r"^\*\*Status:\*\*(.*?)(?:\n\n|\Z)", re.MULTILINE | re.DOTALL)


def _manifest_version() -> str:
    manifest = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = manifest["project"]["version"]
    assert isinstance(version, str)
    return version


def _git(*args: str) -> str | None:
    """Run git in the checkout. ``None`` means the answer is unavailable."""
    executable = shutil.which("git")
    if executable is None:
        return None
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, resolved path, no shell
            [executable, "-C", str(ROOT), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError:  # pragma: no cover - git present but unusable
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def _why_tags_are_unreadable() -> str | None:
    """Why an empty tag list here would prove nothing, or ``None`` if it proves something.

    A missing tag and an unfetched tag look identical from inside the
    checkout. Every check below asks this first, so that "no tag exists" is
    only ever concluded from a checkout that would have carried one.
    """
    if not (ROOT / ".git").exists():
        return f"no .git in {ROOT}: an installed tree carries no tags to read"
    if shutil.which("git") is None:
        return "no git executable on PATH"
    if _git("rev-parse", "--is-inside-work-tree") != "true":
        return "not a git work tree"
    if _git("rev-parse", "--is-shallow-repository") == "true":
        return "shallow checkout: tags are not fetched, so an empty tag list is not evidence"
    if (_git("config", "--get", "remote.origin.tagOpt") or "") == "--no-tags":
        return "clone configured with tagOpt=--no-tags, so tags were never fetched"
    return None


def _release_tags() -> list[str]:
    """Release tags, newest first."""
    listed = _git("tag", "--list", "--sort=-v:refname") or ""
    return [tag for tag in listed.splitlines() if RELEASE_TAG.match(tag.strip())]


def _tag_version(tag: str) -> str:
    matched = RELEASE_TAG.match(tag)
    assert matched is not None, tag
    return matched.group(1)


def _tag_date(tag: str) -> str | None:
    """The tag's own date: the tagger's for an annotated tag, the commit's otherwise."""
    return _git("for-each-ref", "--format=%(creatordate:short)", f"refs/tags/{tag}") or None


def _require_readable_tags() -> list[str]:
    reason = _why_tags_are_unreadable()
    if reason is not None:
        pytest.skip(f"cannot measure the repository's tags: {reason}")
    return _release_tags()


def test_the_citation_names_a_release_that_exists() -> None:
    """A citation to a version nobody can fetch is a citation to nothing.

    `CITATION.cff` is not a restatement of `pyproject.toml`. It is the record a
    reader cites, so it names the newest release that was actually cut, dated
    with that release's own date. When there is no release it says so by
    carrying no date at all.
    """
    tags = _require_readable_tags()
    text = CITATION.read_text(encoding="utf-8")

    cited_versions = CITATION_VERSION.findall(text)
    assert len(cited_versions) == 1, (
        f"expected one top-level version: field, found {cited_versions}"
    )
    cited = cited_versions[0]
    cited_dates = CITATION_DATE.findall(text)

    if not tags:
        assert not cited_dates, (
            "CITATION.cff carries date-released "
            f"{cited_dates[0]!r} and no release tag exists in this repository, "
            "so it dates a release that was never cut"
        )
        return

    by_version = {_tag_version(tag): tag for tag in tags}
    assert cited in by_version, (
        f"CITATION.cff cites version {cited!r}, which is not a tag. "
        f"Declared in pyproject.toml: {_manifest_version()}. "
        f"Newest tag: {tags[0]}. Tags: {', '.join(tags)}. "
        "Cite the newest release that exists, not the version under development."
    )

    tag = by_version[cited]
    released_on = _tag_date(tag)
    assert cited_dates == [released_on], (
        f"CITATION.cff cites {cited!r} with date-released {cited_dates!r}, "
        f"but {tag} is dated {released_on!r}"
    )


def test_the_status_paragraph_names_the_declared_version_and_every_tag() -> None:
    """The release status a reader is shown has to be the one that is true.

    Two failures this makes impossible. Bumping `pyproject.toml` without saying
    what happened to the new number, and cutting a tag while the README still
    says the version is untagged.
    """
    tags = _require_readable_tags()
    declared = _manifest_version()

    status_match = README_STATUS.search(README.read_text(encoding="utf-8"))
    assert status_match is not None, "README.md has no `**Status:**` paragraph"
    status = " ".join(status_match.group(1).split())

    newest = tags[0] if tags else None
    assert declared in status, (
        f"pyproject.toml declares {declared}, and the README's Status paragraph does not "
        f"mention it. Newest tag: {newest or 'none'}. Status paragraph: {status!r}"
    )
    for tag in tags:
        assert tag in status, (
            f"{tag} is tagged in this repository and the README's Status paragraph "
            f"does not name it. Status paragraph: {status!r}"
        )

    declared_is_tagged = declared in {_tag_version(tag) for tag in tags}
    says_untagged = "is not tagged" in status or "no tag" in status.lower()
    if declared_is_tagged:
        assert not says_untagged, (
            f"{declared} is tagged, and the README's Status paragraph still says it is not"
        )
    else:
        assert says_untagged, (
            f"pyproject.toml declares {declared}; the newest tag is {newest or 'none'}, "
            "so nothing was released at the declared version, and the README's Status "
            f"paragraph does not say so. Status paragraph: {status!r}"
        )


def test_the_version_the_package_reports_has_a_changelog_section() -> None:
    """A version with no changelog entry is a release with no record of its changes.

    Keep a Changelog's heading form, so this is the same string a reader
    follows the ``## [Unreleased]`` section down to.
    """
    changelog = CHANGELOG.read_text(encoding="utf-8")
    heading = f"## [{__version__}] - "
    assert heading in changelog, f"CHANGELOG.md has no {heading!r} section"
    assert __version__ == _manifest_version()


def _jobs(workflow: str) -> dict[str, str]:
    """Split a workflow into its jobs, without a YAML parser (this project has none)."""
    lines = workflow.splitlines()
    try:
        first = next(i for i, line in enumerate(lines) if line.rstrip() == "jobs:")
    except StopIteration:  # pragma: no cover - a workflow with no jobs
        return {}
    starts: list[tuple[int, str]] = []
    for index in range(first + 1, len(lines)):
        matched = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", lines[index])
        if matched is not None:
            starts.append((index, matched.group(1)))
    bounds = [*[i for i, _ in starts], len(lines)]
    return {name: "\n".join(lines[bounds[n] : bounds[n + 1]]) for n, (_, name) in enumerate(starts)}


def test_ci_fetches_the_tags_these_checks_read() -> None:
    """Otherwise the checks above skip in CI and gate nothing.

    `actions/checkout` fetches one commit and no tags by default, which is
    exactly the shape `_why_tags_are_unreadable` refuses to read. The job that
    runs `make verify` has to ask for the tags, or the release checks are a
    gate that cannot fail.
    """
    jobs = _jobs(CI_WORKFLOW.read_text(encoding="utf-8"))
    running = {name: body for name, body in jobs.items() if "make verify" in body}
    assert running, ".github/workflows/ci.yml has no job that runs `make verify`"
    for name, body in running.items():
        assert "actions/checkout" in body, f"job {name!r} runs make verify without a checkout"
        assert "fetch-depth: 0" in body, (
            f"job {name!r} checks out shallow, so tests/test_release_metadata.py skips there"
        )
        assert "fetch-tags: true" in body, (
            f"job {name!r} does not fetch tags, so tests/test_release_metadata.py skips there"
        )


#: A `pip install` naming this project's own distribution, in any quoting and
#: with or without an extra. `oscal_validate` too, because pip accepts the
#: underscore spelling and a reader copying it would hit the same wall.
SELF_PIP_INSTALL = re.compile(r"pip install\s+['\"]?oscal[-_]validate")

#: The sentence in the README's Status paragraph that makes the check below
#: apply. When the first upload happens this line goes, and the gate retires
#: itself rather than having to be remembered and deleted.
README_SAYS_NOT_ON_PYPI = "Nothing is published to PyPI"


def _reader_facing_files() -> list[Path]:
    """Every file that hands a *reader* an install command.

    `CHANGELOG.md` and `tests/` are excluded on purpose: both describe past
    states and this defect in the past tense, and a historical record that
    could not quote the broken command would be a worse record.
    """
    files = [README, *sorted((ROOT / "docs").rglob("*.md"))]
    files += sorted((ROOT / "src").rglob("*.py"))
    return files


def test_nothing_hands_a_reader_an_install_command_for_an_unpublished_name() -> None:
    """`pip install oscal-validate` ends at `No matching distribution found`.

    Four places printed it anyway: the README's AI section, its Bedrock
    paragraph, ADR-0005, and two `ModelError` messages in
    `oscal_validate/ai/client.py` -- the last two being what a user reads at
    the moment something has already failed. The README says eight lines from
    its top that nothing is published, so the instruction contradicted the
    status in the same document.

    This is the same shape as the defects this tool reports on: a name that
    resolves to nothing, published as though it resolved to something.
    """
    if README_SAYS_NOT_ON_PYPI not in README.read_text(encoding="utf-8"):
        pytest.skip(
            "the README no longer says nothing is published, so an install command "
            "naming this distribution may now be correct"
        )
    offenders: list[str] = []
    for path in _reader_facing_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if SELF_PIP_INSTALL.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    assert not offenders, (
        "these lines tell a reader to install a distribution that is not on any index, "
        "while README.md says nothing is published:\n  " + "\n  ".join(offenders)
    )
