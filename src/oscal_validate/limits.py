"""What a clean run does not mean, as data, in the README's own words.

``limits.json`` is package data generated from the README's "Limits" section
by ``tools/limits_data.py`` (``make limits-data``), the same way
``docs/CONSTRAINT-COVERAGE.md`` is generated from the vendored metaschema
modules. It is shipped inside the package rather than read from the repository
because the one caller that needs it -- the MCP server -- runs against an
installed copy with no checkout beside it, and a disclosure that is only
available to people who already have the source is not a disclosure.

The generator refuses rather than guesses, and ``tests/test_mcp.py`` fails if
the committed JSON is not what the generator writes today. Between them, the
sentence a reader is shown and the sentence the README publishes cannot come
apart: the failure mode this guards against is a *shorter* list of limits than
the project actually states, which is an absence rendered as an answer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: The generated file, beside this module. ``pyproject.toml`` lists it under
#: ``package-data``; ``tests/test_mcp.py`` fails if that entry is dropped.
LIMITS_PATH = Path(__file__).resolve().parent / "limits.json"


def read_limits() -> dict[str, Any]:
    """The Limits section as data: a preamble and one entry per limit.

    Each entry carries ``title``, the bold lead-in sentence, and ``text``, the
    whole paragraph with its Markdown intact and only its hard line wrapping
    removed. Nothing here is paraphrased.
    """
    loaded: Any = json.loads(LIMITS_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not loaded.get("limits"):
        raise ValueError(f"{LIMITS_PATH} carries no limits; run 'make limits-data'")
    return loaded
