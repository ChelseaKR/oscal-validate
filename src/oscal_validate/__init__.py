"""oscal-validate: deterministic structural validation for OSCAL documents.

Structural conformance is not evidence that a control is implemented. This
tool checks documents; it does not assess systems.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .findings import Finding, Rule, Severity
from .validator import build_session, validate, validate_file

__all__ = [
    "Finding",
    "Rule",
    "Severity",
    "__version__",
    "build_session",
    "validate",
    "validate_file",
]
