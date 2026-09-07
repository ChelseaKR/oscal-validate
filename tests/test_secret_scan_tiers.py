"""The full-history secret scan must stay capable of failing on a revoked leak.

Five properties of `.github/workflows/trufflehog.yml` are asserted here. Each one has silently
un-armed a secret scan somewhere in this portfolio, and none of them shows up
as a red build when it breaks -- the job goes green either way, which is the
whole problem.

1. **The result tiers include `unverified`.** TruffleHog sorts a finding into
   `verified` (it authenticated the credential against the live service),
   `unknown` (verification errored) and `unverified` (it asked, and the service
   said no). A credential that leaked and was later *revoked* -- the normal end
   state of a real incident, and the exact case a scheduled full-history sweep
   exists to catch -- answers "no" and is therefore `unverified`. A scan
   configured `--only-verified`, `--results=verified`, or
   `--results=verified,unknown` cannot fail on it. Measured 2026-09-06 on a
   throwaway clone with a real-shaped AWS key planted in one commit and deleted
   in the next: the first three exited 0 reporting nothing; adding `unverified`
   exited 183 with `unverified_secrets: 1`.

2. **No lane uses `--only-verified`.** It is the same hole under a different
   name, and it reads like a deliberate choice rather than a gap.

3. **The action ref and the `version:` input name the same release.** The
   `version:` input is what selects the scanning binary
   (`ghcr.io/trufflesecurity/trufflehog:${VERSION}`); the `uses:` SHA pins only
   the wrapper. Omitting the input entirely is worse than a mismatch, because
   the action then defaults to `latest` and the SHA pin describes nothing that
   scans. Dependabot edits `uses:` and never a `with:` input, so the two drift
   apart and each "upgrade" is a no-op that reads like one.

4. **`fetch-depth: 0` survives on the checkout.** Without it `actions/checkout`
   fetches a single commit and a "full-history" sweep becomes a one-commit scan
   that still reports success.

5. **`path: ./` survives.** With path, base and head all unset the action exits
   on its own "BASE and HEAD commits are the same" guard, having scanned
   nothing, and still reports success.

The pin comment is a YAML comment and so is invisible to a YAML parser: these
assertions read the workflow as text on purpose.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "trufflehog.yml"

# The tier a revoked credential lands in. Its absence is the defect.
REQUIRED_RESULT_TIER = "unverified"

_PINNED = re.compile(
    r"trufflesecurity/trufflehog@[0-9a-f]{40}\s*#\s*v(\d+(?:\.\d+)*)",
)
_SELECTED = re.compile(r"^\s*version:\s*[\"']?(\d+(?:\.\d+)*)[\"']?\s*$", re.MULTILINE)
_EXTRA_ARGS = re.compile(r"^\s*extra_args:\s*(.+?)\s*$", re.MULTILINE)
_FETCH_DEPTH_ZERO = re.compile(r"^\s*fetch-depth:\s*0\s*(?:#.*)?$", re.MULTILINE)
_SCAN_PATH = re.compile(r"^\s*path:\s*\./\s*(?:#.*)?$", re.MULTILINE)


def _workflow_text() -> str:
    assert WORKFLOW.is_file(), (
        f"{WORKFLOW} is missing. If the full-history secret scan was deliberately "
        "removed or replaced, update this test with the replacement rather than "
        "deleting it -- an absent scan must be a decision, not a silence."
    )
    return WORKFLOW.read_text(encoding="utf-8")


def _lanes() -> list[str]:
    lanes = _EXTRA_ARGS.findall(_workflow_text())
    assert lanes, (
        f"no `extra_args:` found in {WORKFLOW.name}; this guard can no longer see "
        "which result tiers the scan reports on."
    )
    return lanes


def test_no_lane_uses_only_verified() -> None:
    for args in _lanes():
        assert "--only-verified" not in args, (
            "`--only-verified` cannot fail on a credential the provider has already "
            "revoked, which is the normal end state of a real leak and the case this "
            f"scan exists for. Offending args: {args!r}"
        )
        assert re.search(r"--results=[\w,]+", args), (
            f"expected an explicit `--results=` tier list, got {args!r}"
        )


def test_some_lane_reports_the_unverified_tier() -> None:
    tier_lists = [
        match.group(1).split(",")
        for args in _lanes()
        if (match := re.search(r"--results=([\w,]+)", args))
    ]
    assert any(REQUIRED_RESULT_TIER in tiers for tiers in tier_lists), (
        f"no lane of this scan reports `{REQUIRED_RESULT_TIER}` results (found "
        f"{tier_lists}), so nothing here can fail on a credential that leaked and "
        "was then revoked. Measured: verified and verified,unknown both exit 0 on a "
        "planted-then-deleted AWS key; adding unverified exits 183."
    )


def test_action_ref_and_version_input_name_the_same_release() -> None:
    text = _workflow_text()
    pinned = _PINNED.findall(text)
    selected = _SELECTED.findall(text)

    assert pinned, (
        "could not read a SHA-pinned trufflesecurity/trufflehog ref and its "
        f"`# vX.Y.Z` comment in {WORKFLOW.name}"
    )
    assert selected, (
        f"no `version:` input on the trufflehog step in {WORKFLOW.name}. Without it "
        'the action defaults to "latest", so the SHA pin above it pins only the '
        "wrapper and not the binary that actually scans."
    )
    assert len(pinned) == len(selected), (
        f"{len(pinned)} pinned trufflehog ref(s) but {len(selected)} `version:` "
        "input(s); every trufflehog step needs its own pinned version"
    )
    for ref_version, input_version in zip(pinned, selected, strict=True):
        assert ref_version == input_version, (
            f"the action is pinned to v{ref_version} but `version: {input_version}` "
            f"is what downloads the scanner, so the scan runs {input_version} and the "
            f"bump to v{ref_version} changed nothing. Set them to the same release."
        )


def test_checkout_keeps_full_history() -> None:
    text = _workflow_text()
    assert "actions/checkout@" in text, "the scan no longer checks the repository out"
    assert _FETCH_DEPTH_ZERO.search(text), (
        "`fetch-depth: 0` is missing from the checkout. actions/checkout then fetches "
        "a single commit and this full-history sweep silently becomes a one-commit "
        "scan that still reports success."
    )


def test_scan_walks_the_whole_repository() -> None:
    assert _SCAN_PATH.search(_workflow_text()), (
        "`path: ./` is missing; with path, base and head all unset the action exits "
        'on its own "BASE and HEAD commits are the same" guard having scanned nothing.'
    )
