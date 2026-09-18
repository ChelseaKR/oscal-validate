"""The full-history secret scan must stay capable of failing on a revoked leak.

Six properties of `.github/workflows/trufflehog.yml` are asserted here. Each one has silently
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

4. **The scan is invoked over the whole history: `base: ''` and `head: HEAD`.**
   This, and not the checkout depth, is what decides how much gets read. The
   action picks its range from the triggering event unless one of `base`/`head`
   is non-empty: `push` scans `--since-commit <event.before> --branch
   <event.after>`, `pull_request` scans the PR's own base..head diff, and only
   `schedule` and `workflow_dispatch` pass an empty `--since-commit`, i.e.
   everything. So until 2026-09-13 the weekly cron and a manual dispatch here
   did read history, while every push to main and every pull_request -- the
   runs that gate a merge -- read the event's diff and reported it under the
   job name "full-history secret scan (all result tiers)". `head` must be
   non-empty: the action reaches its explicit-range branch on
   `[ -n "$BASE" ] || [ -n "$HEAD" ]`, so `base: ''` alone leaves both empty
   and falls straight back to the event logic. `HEAD` rather than a branch name
   because a `pull_request` checkout is a detached merge ref with no branch to
   name. Measured on a throwaway clone with a real-shaped AWS key planted in
   one commit and deleted in the next: the event-derived diff range exits 0,
   `--since-commit "" --branch HEAD` exits 183.

5. **`fetch-depth: 0` survives on the checkout.** A necessary precondition, and
   NOT the cause. Without it `actions/checkout` fetches a single commit and
   there is no history on disk for the scanner to walk -- but full depth was
   checked out here the whole time the push and pull_request runs were reading
   a diff, so this workflow is itself the proof that depth alone arms nothing.
   Depth decides what git has; `base`/`head` decide what is read.

6. **`path: ./` survives.** It is the step's `working-directory` and the
   directory the action bind-mounts into the scanner container, so pointing it
   anywhere but the repository root scans somewhere else, or nothing. With
   `head` set the action also resolves it there, and a path that is not a git
   repository now fails loudly on the action's "BASE and HEAD commits are the
   same" guard rather than going green.

The pin comment is a YAML comment and so is invisible to a YAML parser: these
assertions read the workflow as text on purpose. The invocation assertions read
it with comments STRIPPED, because the comment beside the fix quotes the very
strings they look for, and four conformance checks elsewhere in this portfolio
passed by matching a tool name inside a comment.
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
_FETCH_DEPTH_ZERO = re.compile(r"^\s*fetch-depth:\s*0\s*$", re.MULTILINE)
_SCAN_PATH = re.compile(r"^\s*path:\s*\./\s*$", re.MULTILINE)
# The two inputs that make the action skip its per-event range logic and scan
# every commit reachable from the checkout.
_BASE_EMPTY = re.compile(r"^\s*base:\s*(?:''|\"\")\s*$", re.MULTILINE)
_HEAD_IS_HEAD = re.compile(r"^\s*head:\s*(?:HEAD|'HEAD'|\"HEAD\")\s*$", re.MULTILINE)


def _workflow_text() -> str:
    assert WORKFLOW.is_file(), (
        f"{WORKFLOW} is missing. If the full-history secret scan was deliberately "
        "removed or replaced, update this test with the replacement rather than "
        "deleting it -- an absent scan must be a decision, not a silence."
    )
    return WORKFLOW.read_text(encoding="utf-8")


def _workflow_code(text: str | None = None) -> str:
    """The workflow with its YAML comments removed, quote-aware.

    The comment documenting the fix quotes `base: ''` and `head: HEAD` verbatim,
    so an assertion over the raw text would pass on prose describing the setting
    rather than on the setting itself.
    """
    stripped: list[str] = []
    for line in (_workflow_text() if text is None else text).splitlines():
        quote = ""
        cut: int | None = None
        for index, char in enumerate(line):
            if quote:
                if char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char == "#" and (index == 0 or line[index - 1] in " \t"):
                cut = index
                break
        stripped.append(line if cut is None else line[:cut].rstrip())
    return "\n".join(stripped)


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


def test_the_comment_stripper_actually_strips() -> None:
    """A stripper that silently no-ops would put the invocation assertions back on prose."""
    sample = "with:\n  base: ''  # `base: ''` plus `head: HEAD` is the fix\n  x: \"a # b\"\n"
    code = _workflow_code(sample)
    assert "head: HEAD" not in code, f"comment survived stripping: {code!r}"
    assert '  x: "a # b"' in code, f"a `#` inside quotes was treated as a comment: {code!r}"


def test_the_scan_is_invoked_over_the_whole_history() -> None:
    code = _workflow_code()
    assert _BASE_EMPTY.search(code), (
        "`base: ''` is missing from the trufflehog step. Without an explicit range the "
        "action derives one from the triggering event: a push scans "
        "`--since-commit <event.before> --branch <event.after>` and a pull_request scans "
        "the PR's own base..head diff, so the two events that gate a merge sweep a diff "
        'while reporting under the job name "full-history secret scan".'
    )
    assert _HEAD_IS_HEAD.search(code), (
        "`head: HEAD` is missing from the trufflehog step. It is the half that actually "
        'switches the action over: it takes the explicit-range branch on `[ -n "$BASE" ] '
        "|| [ -n \"$HEAD\" ]`, so `base: ''` on its own leaves both empty and falls back "
        "to the per-event logic. It must be `HEAD` rather than a branch name, because a "
        "pull_request is checked out at a detached merge ref with no branch to name."
    )


def test_checkout_keeps_full_history() -> None:
    """`fetch-depth: 0` is necessary and not sufficient; see item 5 of the module docstring."""
    code = _workflow_code()
    assert "actions/checkout@" in code, "the scan no longer checks the repository out"
    assert _FETCH_DEPTH_ZERO.search(code), (
        "`fetch-depth: 0` is missing from the checkout, so actions/checkout fetches a "
        "single commit and there is no history on disk for the scanner to walk. Note "
        "that this is only the precondition: full depth was checked out here the whole "
        "time the push and pull_request runs were reading the event's diff. What is "
        "read is decided by `base`/`head`, asserted separately."
    )


def test_scan_walks_the_whole_repository() -> None:
    assert _SCAN_PATH.search(_workflow_code()), (
        "`path: ./` is missing; it is the step's working-directory and the directory the "
        "action bind-mounts into the scanner container, so anything else scans somewhere "
        "other than the repository root, or nothing."
    )
