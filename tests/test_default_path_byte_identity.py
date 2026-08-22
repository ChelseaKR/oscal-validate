"""The default validation path is byte-identical to what it was before the AI layer.

``tests/golden/`` holds the exact stdout and exit code of ``oscal-validate``
over the fixtures and over eight published NIST documents, captured from
commit 6978895 -- the last commit before any model-backed command existed.
Every later commit has to reproduce those bytes. This is the proof behind the
README's claim that the opt-in commands changed nothing about the command
that was already there.

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
