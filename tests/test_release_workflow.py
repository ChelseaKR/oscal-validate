"""The release path, held to the posture it claims.

This repository had no release workflow and no publish path at all: it carried
tags `v0.1.0` and `v0.2.0`, and `pypi.org/pypi/oscal-validate` returned
nothing, so `pip install oscal-validate` could not work and the tags
advertised versions that existed nowhere installable.

`.github/workflows/release.yml` is that path. Every property asserted here is
one where getting it wrong is silent -- the workflow would still run, still go
green, and still publish -- so each is checked mechanically rather than left
to the review that wrote the file.

The properties, and what each one refuses:

- **Dispatch-only.** A `push: tags:` trigger runs the workflow definition
  stored *at the tagged ref*, so whoever can push a tag also picks the release
  workflow. Dispatching from `main` keeps the release authority on the
  reviewed branch.
- **The authorization is the standards-owned reusable workflow, pinned to a
  full commit SHA.** A branch or moving-tag pin is a mutable trust anchor.
- **The product gate re-runs at the tagged commit.** A PR's earlier green tick
  is not evidence about the commit being shipped.
- **Trusted Publishing, never a stored token.** A long-lived PyPI token is a
  credential that can leak; OIDC is a short-lived identity that cannot.
- **The publisher never rebuilds.** A second build's output is not the
  artifact the Sigstore attestation covers, and PyPI is not revocable.
- **The digests are re-checked before the upload**, so what is published is
  what was attested.
- **The GitHub release job never checks out repository code**, because it is
  the one job holding `contents: write`.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
ALLOWED_SIGNERS = ROOT / ".github" / "allowed_signers"

AUTHORIZE = "ChelseaKR/.github/.github/workflows/release-authorize.yml"


def _text() -> str:
    assert WORKFLOW.is_file(), (
        f"{WORKFLOW} is missing. If the release path was deliberately removed, "
        "delete this file in the same commit and say why."
    )
    return WORKFLOW.read_text(encoding="utf-8")


def _uncommented(text: str | None = None) -> str:
    """The workflow with every comment line removed.

    A check that matches inside a comment is a check that passes on prose.
    This file's own subject explains why a ``push: tags:`` trigger is wrong,
    in a comment, and the first draft of the test below matched that
    explanation and went green for it. Four conformance checks across this
    portfolio were measured doing exactly that in 2026-09; strip first.
    """
    body = _text() if text is None else text
    return "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))


def _job(name: str) -> str:
    """One job's block, from its key to the next job at the same indent."""
    text = _text()
    start = text.index(f"\n  {name}:\n")
    rest = text[start + 1 :]
    following = re.search(r"\n  [a-z][a-z-]*:\n", rest)
    return rest[: following.start()] if following else rest


def test_the_release_is_dispatched_and_never_fires_on_a_tag_push() -> None:
    text = _uncommented()
    assert "workflow_dispatch:" in text
    trigger = text.split("jobs:", 1)[0]
    assert "push:" not in trigger, (
        "a push trigger would run the workflow definition stored at the tagged ref"
    )
    assert "tags:" not in trigger
    assert "pull_request" not in trigger


def test_the_authorization_is_the_shared_workflow_pinned_to_a_commit() -> None:
    text = _text()
    match = re.search(rf"uses:\s*{re.escape(AUTHORIZE)}@([0-9a-f]+)", text)
    assert match, "the release does not call the standards release-authorize workflow"
    assert len(match.group(1)) == 40, "the authorization workflow must be pinned to a full SHA"


def test_every_job_that_matters_waits_for_the_authorization() -> None:
    for job in ("verify", "build", "github-release", "pypi-publish"):
        block = _job(job)
        assert "needs:" in block, job
        assert "authorize" in block.split("needs:", 1)[1][:80], f"{job} does not need authorize"


def test_the_signing_key_is_committed_and_is_one_ed25519_key_for_the_owner() -> None:
    assert ALLOWED_SIGNERS.is_file(), (
        "release-authorize verifies the tag signature against this file; without it "
        "no tag can be authorized"
    )
    lines = [
        line
        for line in ALLOWED_SIGNERS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert len(lines) == 1, lines
    assert lines[0].startswith("3114598+ChelseaKR@users.noreply.github.com ")
    assert 'namespaces="git"' in lines[0], "the key should be scoped to git signatures"
    assert " ssh-ed25519 AAAAC3NzaC1lZDI1NTE5" in lines[0]
    assert "PRIVATE KEY" not in ALLOWED_SIGNERS.read_text(encoding="utf-8")


def test_the_merge_blocking_gate_reruns_at_the_tagged_commit() -> None:
    verify = _job("verify")
    assert "make verify" in verify
    assert "needs.authorize.outputs.release-commit" in verify, (
        "the gate must run at the commit the verified tag names, not at a ref re-resolved here"
    )


def test_the_tag_the_package_and_the_changelog_must_agree_before_anything_ships() -> None:
    verify = _job("verify")
    assert "pyproject.toml" in verify and "CHANGELOG.md" in verify
    assert "version mismatch" in verify


def test_pypi_publishes_over_oidc_and_no_token_is_stored_anywhere() -> None:
    text = _uncommented()
    publish = _job("pypi-publish")
    assert "id-token: write" in publish
    assert "environment:" in publish and "name: pypi" in publish
    assert "pypa/gh-action-pypi-publish@" in publish
    # A stored token would be the whole point undone.
    assert "password:" not in text
    assert "PYPI_API_TOKEN" not in text
    assert "TWINE_" not in text
    assert "secrets." not in text, "the release path needs no repository secret"


def test_the_publisher_never_rebuilds_what_it_publishes() -> None:
    publish = _uncommented(_job("pypi-publish"))
    for rebuild in ("uv build", "python -m build", "actions/checkout@"):
        assert rebuild not in publish, (
            f"{rebuild!r} in the publish job: a rebuilt artifact is not the one that was attested"
        )
    assert "sha256sum -c SHA256SUMS" in publish, (
        "the published bytes are not checked against the attested manifest"
    )


def test_the_release_job_holding_write_never_checks_out_repository_code() -> None:
    release = _uncommented(_job("github-release"))
    assert "contents: write" in release
    assert "actions/checkout@" not in release
    assert "download-artifact@" in release


def test_publication_rechecks_the_tag_object_it_was_authorized_for() -> None:
    """A tag moved between authorization and publication must stop the run."""
    for job in ("github-release", "pypi-publish"):
        block = _job(job)
        assert "tag-object-sha" in block, job
        assert "git/ref/tags/" in block, job


def test_the_github_release_step_is_idempotent() -> None:
    release = _job("github-release")
    assert "gh release view" in release and "gh release create" in release
    assert "--clobber" in release, "a re-run must be able to replace an asset it already uploaded"


def test_the_build_attests_provenance_and_an_sbom_over_the_shipped_artifacts() -> None:
    build = _job("build")
    assert "actions/attest-build-provenance@" in build
    assert "cyclonedx" in build.lower()
    assert "--validate" in build, "an SBOM generated without --validate cannot fail on a bad schema"
    assert "sha256sum" in build, "the publish jobs need a manifest of the attested bytes"


def test_nothing_on_the_release_path_reuses_a_cache() -> None:
    """A cache hit is an unverified input into an artifact about to be signed."""
    text = _text()
    assert "enable-cache: true" not in text
    assert text.count("enable-cache: false") == len(re.findall(r"astral-sh/setup-uv@", text))


def test_no_step_on_the_release_path_can_fail_softly() -> None:
    text = _uncommented()
    for bypass in ("continue-on-error", "|| true", "|| :", "if-no-files-found: warn"):
        assert bypass not in text, bypass


def test_the_published_version_is_installed_back_and_run() -> None:
    """`pypi-publish` exiting 0 says the upload did not error. This says the
    thing on the index installs and runs."""
    published = _job("verify-published")
    assert "gh attestation verify" in published
    assert "oscal-validate==${RELEASE_TAG#v}" in published


def test_the_tag_name_is_never_interpolated_into_a_shell_body() -> None:
    """``${{ }}`` into ``run:`` is a template-injection vector, and a tag name
    is attacker-influenced for anyone who can push a tag. It travels through
    ``env:`` instead."""
    text = _uncommented()
    assert "RELEASE_TAG: ${{ github.event.inputs.tag }}" in text
    injected = re.findall(r"^\s*\S.*\$\{\{\s*github\.event\.inputs\.tag\s*\}\}", text, re.M)
    # Exactly two: the env: assignment, and the typed input passed to the
    # reusable workflow. Neither is a shell body.
    assert len(injected) == 2, injected
