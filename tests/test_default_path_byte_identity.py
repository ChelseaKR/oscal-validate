"""The default validation path is byte-identical to what it was before the AI layer.

``tests/golden/`` holds the exact stdout and exit code of ``oscal-validate``
over the fixtures and over eight cached public documents -- seven of NIST's and
EasyDynamics' derivative of NIST's ssp-example -- captured from commit 6978895,
the last commit before any model-backed command existed. Every later commit has
to reproduce those bytes. This is the proof behind the README's claim that the
opt-in commands changed nothing about the command that was already there.

Re-captured five times since. Each reason is recorded here because a golden
re-captured without one stops being evidence, and each entry names the pull
request that made it so a reader can check the diff rather than take the
description on trust. The pull request is cited rather than the commit because
these land as squash merges: the SHA does not exist when the entry is written,
and the number does.

This list was itself wrong twice, which is the reason for the citations. It
said "re-captured twice" while carrying two of the four entries below, and it
and the README named *different* pairs -- so between them the two documents
recorded three of the four recaptures and neither said so. The fourth, #81, was
recorded in neither.

On 2026-08-29 (#35): the ``CONSTRAINT_NOT_EVALUATED`` finding for
``allowed-values`` carried a sentence that said something false about NIST's
``allow-other`` semantics, and correcting a sentence the report prints is a
change to the report.

On 2026-09-01 (#30): eleven ``matches`` constraints became evaluated, so the one
line that counts the unevaluated ones went from 25 to 14. That is the whole
diff: two lines in each of the twelve cases, in both formats, and no document
gained or lost a finding. Every published document in the corpus conforms to all
eleven, which is why the evidence that those checks can fail is in
tests/test_break_the_gate.py rather than here.

On 2026-09-02 (#38), cutting 0.3.0: the JSON report stamps ``tool.version``, so
the version bump moves that one line and nothing else. The whole diff is twelve
lines, one per JSON golden; the twelve text goldens are untouched because the
text format does not print the version, and no document gained or lost a
finding. A recapture whose diff is anything more than the version stamp is not
this one, and should not be committed as if it were.

On 2026-09-06 (#81): every JSON report gained ``report_schema_version``, so the
whole diff is twelve lines, one per JSON golden, and the twelve text goldens are
untouched because the text format does not print it. No document gained or lost
a finding. This recapture went unrecorded here and in the README for a day,
while both documents still said the goldens had moved exactly twice.

On 2026-09-07 (#PENDING), cutting 0.4.0: the same one line as #38, for the same
reason -- the JSON report stamps ``tool.version``, so a version bump moves that
line and nothing else. Twelve lines, one per JSON golden; the twelve text
goldens are untouched because the text format does not print the version, and
no document gained or lost a finding. Verified before committing by reading the
whole diff: every changed line is ``"version": "0.3.0"`` becoming
``"version": "0.4.0"``.

Nothing enforces this list. A test that checked it against ``git log`` would
have to name the recapture commit inside the commit that makes it, and a
count gated on equality would go red on whoever is doing the recapture
correctly, at the moment they do it. So it is maintained by hand, and the
citations are what make a hand-maintained record checkable.

The cached NIST documents are not committed (they are public and large, and
``.survey-cache/`` is how the survey harness keeps them); their goldens are
keyed by SHA-256 so the comparison is skipped when the cache is absent and
refused when the file at that path is not the one the golden was captured
from.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from .golden.capture import CACHE, CACHED, CASES, FIXTURES, GOLDEN, run

MANIFEST = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))


def _cases() -> list[tuple[str, Path, list[Path]]]:
    cases = list(CASES)
    for name, relative in CACHED:
        if name in MANIFEST:
            cases.append((name, CACHE / relative, []))
    return cases


@pytest.mark.parametrize(("name", "document", "resolve"), _cases())
@pytest.mark.parametrize("fmt", ["text", "json"])
def test_default_path_reproduces_the_golden_bytes(
    name: str, document: Path, resolve: list[Path], fmt: str
) -> None:
    recorded = MANIFEST[name]
    if not document.is_file():
        assert not recorded["committed"], f"committed fixture missing: {document}"
        pytest.skip(f"{document.name} is not in the local cache")
    digest = hashlib.sha256(document.read_bytes()).hexdigest()
    assert digest == recorded["sha256"], (
        f"{document} is not the file the golden was captured from; refusing to compare"
    )
    expected = (GOLDEN / f"{name}.{fmt}.out").read_bytes()
    assert run(document, resolve, fmt) == expected, f"{name} ({fmt}) drifted from the golden"


def test_every_committed_golden_case_is_exercised() -> None:
    names = {name for name, _, _ in CASES} | {name for name, _ in CACHED}
    assert set(MANIFEST) <= names
    for name in MANIFEST:
        for fmt in ("text", "json"):
            assert (GOLDEN / f"{name}.{fmt}.out").is_file(), name


def test_the_default_path_never_imports_the_ai_layer() -> None:
    """Running ``validate`` must not load ``oscal_validate.ai`` or the SDK.

    The lazy import is the mechanism; this is the check that it held. A fresh
    interpreter runs a validation end to end and then reports every loaded
    module whose name starts with the two names that must be absent.
    """
    script = (
        "import sys\n"
        "from oscal_validate.cli import main\n"
        f"main([{str(FIXTURES / 'clean_catalog.json')!r}])\n"
        "loaded = sorted(m for m in sys.modules if m.startswith(('oscal_validate.ai', "
        "'anthropic', 'httpx', 'boto')))\n"
        "print(loaded)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "[]"
