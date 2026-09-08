"""oscal-validate: deterministic structural validation for OSCAL documents.

Structural conformance is not evidence that a control is implemented. This
tool checks documents; it does not assess systems.
"""

from __future__ import annotations

#: Pinned to pyproject.toml's version by tests/test_cli.py. Not read from
#: importlib.metadata: the GitHub Action runs this package straight off
#: PYTHONPATH with nothing installed, and there is no distribution to ask.
__version__ = "0.4.0"

from .findings import Acknowledgement, Finding, Rule, Severity
from .report import REPORT_SCHEMA_VERSION, read_report_schema
from .validator import build_session, validate, validate_file

#: The public library surface. Everything here is documented in docs/API.md
#: with a stability promise; everything not here is internal and may move in
#: any release. ``tests/test_public_api.py`` pins these names and their
#: signatures, so widening or narrowing this list is a deliberate act.
__all__ = [
    "REPORT_SCHEMA_VERSION",
    "Acknowledgement",
    "Finding",
    "Rule",
    "Severity",
    "__version__",
    "build_session",
    "read_report_schema",
    "validate",
    "validate_file",
]
