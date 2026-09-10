"""Generate src/oscal_validate/limits.json from the README's Limits section.

The MCP server's ``limits`` tool exists so an assistant can be told what a
clean run does not mean, in the project's own published words rather than in a
paraphrase a model composed. Those words live in one place -- the README's
"Limits" section -- and this script is what carries them into the package,
where an installed copy can read them without the repository beside it.

Generated, not hand-maintained, for the same reason
``docs/CONSTRAINT-COVERAGE.md`` is: a second copy of a disclosure is a copy
that goes stale, and a stale disclosure is worse than none because it is
believed. ``tests/test_mcp.py`` fails if the committed JSON is not what this
script writes today, so the README and the served answer cannot drift apart.

    uv run python tools/limits_data.py src/oscal_validate/limits.json

Every refusal below is deliberate. A parser that shrugged and emitted the
paragraphs it happened to understand would publish a *shorter* list of limits
than the README states, which is the exact shape of defect this project exists
to report: an absence rendered as an answer.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

#: The heading the section opens with, and the level the next section is at.
HEADING = "\n## Limits\n"
NEXT_HEADING = "\n## "

#: The bold lead-in that opens every limit. The README's own convention: each
#: limit is one paragraph whose first sentence is bold and says, in the
#: present tense, a thing the tool does not do.
LEAD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


class LimitsError(RuntimeError):
    """The README's Limits section is not the shape this reader knows."""


def _paragraphs(markdown: str) -> list[str]:
    return [block.strip() for block in markdown.split("\n\n") if block.strip()]


def section(readme: str) -> str:
    """The Limits section's body, between its heading and the next one."""
    start = readme.find(HEADING)
    if start < 0:
        raise LimitsError(f"{README.name} has no '## Limits' heading")
    body = readme[start + len(HEADING) :]
    end = body.find(NEXT_HEADING)
    if end < 0:
        raise LimitsError("the Limits section runs to the end of the file with no section after it")
    return body[:end]


def parse(readme: str) -> dict[str, object]:
    """The Limits section as data, or a refusal naming what it could not read."""
    blocks = _paragraphs(section(readme))
    if len(blocks) < 2:
        raise LimitsError(
            f"the Limits section has {len(blocks)} paragraph(s); expected a preamble "
            "and at least one limit"
        )
    preamble, rest = blocks[0], blocks[1:]
    if preamble.startswith("**"):
        raise LimitsError(
            "the first paragraph of the Limits section opens in bold, so this reader "
            "cannot tell the preamble from a limit"
        )
    limits: list[dict[str, str]] = []
    for block in rest:
        if not block.startswith("**"):
            raise LimitsError(
                "a paragraph in the Limits section does not open with a bold lead-in and "
                f"would be dropped: {block[:60]!r}"
            )
        found = LEAD.match(block)
        if found is None:  # pragma: no cover - startswith('**') without a closing '**'
            raise LimitsError(f"a bold lead-in is never closed: {block[:60]!r}")
        limits.append({"title": _flatten(found.group(1)), "text": _flatten(block)})
    return {
        "source": 'README.md, "Limits"',
        "preamble": _flatten(preamble),
        "limits": limits,
    }


def _flatten(markdown: str) -> str:
    """One paragraph on one line, Markdown intact.

    Only the hard line wrapping is removed. Nothing else is rewritten: the
    backticks, the links and the emphasis are the README's own bytes, and a
    reader that reformatted them would be quoting a sentence nobody wrote.
    """
    return " ".join(markdown.split())


def render() -> str:
    return json.dumps(parse(README.read_text(encoding="utf-8")), indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    destination = (
        Path(argv[1]) if len(argv) > 1 else ROOT / "src" / "oscal_validate" / "limits.json"
    )
    destination.write_text(render(), encoding="utf-8")
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
