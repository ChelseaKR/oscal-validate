"""Capture golden outputs of the default validation path.

Run this only from a commit whose output is the one to be preserved. The
byte-identity test (tests/test_default_path_byte_identity.py) compares the
live tool against these files, so regenerating them is a deliberate act that
belongs in its own commit with its reason.

    uv run python tests/golden/capture.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN = Path(__file__).resolve().parent
FIXTURES = ROOT / "tests" / "fixtures"
CACHE = ROOT / ".survey-cache"

#: (golden name, document, resolve paths). Fixtures are committed; the cached
#: public documents are identified by SHA-256 so the test can skip them when
#: the cache is absent and refuse to compare against a different file.
CASES: list[tuple[str, Path, list[Path]]] = [
    ("clean_catalog", FIXTURES / "clean_catalog.json", []),
    ("clean_profile", FIXTURES / "clean_profile.json", []),
    ("clean_profile_resolved", FIXTURES / "clean_profile.json", [FIXTURES / "clean_catalog.json"]),
]

CACHED: list[tuple[str, str]] = [
    ("nist_ssp_example", "a0d776f49281/ssp-example.json"),
    ("nist_ifa_ssp", "af4e260d18f8/ifa_ssp-example.json"),
    ("nist_ifa_ap", "5db10a22311b/ifa_assessment-plan.json"),
    ("nist_ifa_ar", "90962d7fecee/ifa_assessment-results-example.json"),
    ("nist_component_definition", "8a0ae7a418ef/component-definition-example.json"),
    ("nist_basic_profile", "5818f69c54db/basic_profile.json"),
    ("nist_basic_catalog", "ad7b8c5aec29/basic_catalog.json"),
    ("nist_sp800_53_catalog", "389bfbe57292/NIST_SP-800-53_rev5_catalog.json"),
]


def run(document: Path, resolve: list[Path], fmt: str) -> bytes:
    """The default path's exact bytes, plus its exit code, with one substitution.

    An IMPORT_RESOLVED finding names the resolved absolute path of the file an
    import matched, so the bytes carry the checkout's location. That one
    string is replaced by a placeholder on both sides of the comparison; no
    other byte is touched.
    """
    command = [sys.executable, "-m", "oscal_validate", str(document), "--format", fmt]
    for path in resolve:
        command += ["--resolve", str(path)]
    result = subprocess.run(command, capture_output=True, check=False, cwd=ROOT)
    output = result.stdout + f"\n[exit {result.returncode}]\n".encode()
    return output.replace(str(ROOT).encode(), b"<ROOT>")


def main() -> None:
    manifest: dict[str, dict[str, object]] = {}
    cases = list(CASES)
    for name, relative in CACHED:
        path = CACHE / relative
        if path.is_file():
            cases.append((name, path, []))
    for name, document, resolve in cases:
        for fmt in ("text", "json"):
            (GOLDEN / f"{name}.{fmt}.out").write_bytes(run(document, resolve, fmt))
        manifest[name] = {
            "document": document.name,
            "sha256": hashlib.sha256(document.read_bytes()).hexdigest(),
            "resolve": [p.name for p in resolve],
            "committed": document.is_relative_to(FIXTURES),
        }
    (GOLDEN / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"captured {len(cases)} case(s)")


if __name__ == "__main__":
    main()
