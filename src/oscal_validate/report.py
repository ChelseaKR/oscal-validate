"""The published shape of ``--format json``, and the version of that shape.

``--format json`` is not a debugging convenience. The GitHub Action reads its
``summary`` counts to apply ``fail-on``, the survey harness reads its
``findings``, and anything wiring this tool into a pipeline reads both. Until
now the shape was defined only by the function that writes it, which means a
renamed key would have been a silent change to every consumer -- and for a
consumer that reads a count out of ``summary``, a silently missing key reads
as zero, which is a clean gate. That is the defect this tool exists to catch,
in the tool's own output.

So the shape is published, as ``report.schema.json`` beside this module, and
every report says which version of it the report conforms to.

``REPORT_SCHEMA_VERSION`` moves independently of the tool's version:

- the **major** part changes when a consumer that reads the current shape
  would break -- a key removed or renamed, a type changed, a value that used
  to be present becoming optional;
- the **minor** part changes when a key is added that a consumer may ignore;
- the **patch** part changes when only the schema's own prose changes.

The schema sets ``additionalProperties: false`` throughout, so a consumer that
validates its input learns about a new key rather than passing over it. That
makes a minor bump visible to anyone who checks, which is the point: the
alternative is a consumer silently reading a report it does not understand.
"""

from __future__ import annotations

from pathlib import Path

#: The version of ``report.schema.json``, stamped into every JSON report.
#: See the module docstring for what each part means.
REPORT_SCHEMA_VERSION = "1.0.0"

#: The schema itself, shipped as package data so an installed copy can print
#: it. ``pyproject.toml`` lists it under ``package-data``;
#: ``tests/test_report_schema.py`` fails if that entry is dropped.
REPORT_SCHEMA_PATH = Path(__file__).resolve().parent / "report.schema.json"


def read_report_schema() -> str:
    """The schema as published, byte for byte."""
    return REPORT_SCHEMA_PATH.read_text(encoding="utf-8")
