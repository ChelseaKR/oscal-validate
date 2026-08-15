"""Generate docs/CONSTRAINT-COVERAGE.md from the vendored metaschema files.

The coverage table is not written by hand and is not allowed to drift: it is
produced from the same parse the validator uses, and
``tests/test_constraint_coverage.py`` fails if the committed file does not
match what this script produces.

    uv run python tools/constraint_coverage.py docs/CONSTRAINT-COVERAGE.md
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from oscal_validate.metaschema import Metaschema, load_metaschema  # noqa: E402
from oscal_validate.rules import OSCAL_RELEASE, RETRIEVED  # noqa: E402

HEADER = f"""# Which of NIST's published constraints this tool evaluates

Generated from the vendored metaschema files for OSCAL {OSCAL_RELEASE}
(retrieved {RETRIEVED}) by `tools/constraint_coverage.py`. Do not edit by hand:
`make coverage-doc` regenerates it and `tests/test_constraint_coverage.py`
fails if it is stale.

This file exists because "no findings" and "every published constraint passed"
are different claims, and only the first one is ever true here. Every
constraint NIST publishes is listed below with whether this tool runs it, and
where it does not, the reason.
"""


def render() -> str:
    metaschema = load_metaschema()
    total = len(metaschema.constraints)
    evaluated = metaschema.evaluated()
    kinds = Counter(c.kind for c in metaschema.constraints)
    run_kinds = Counter(c.kind for c in evaluated)

    lines = [HEADER, "## Summary", ""]
    lines.append(f"{len(evaluated)} of {total} published constraints are evaluated.")
    lines.append("")
    lines.append("| Constraint kind | Published | Evaluated |")
    lines.append("|---|---:|---:|")
    for kind in sorted(kinds):
        lines.append(f"| `{kind}` | {kinds[kind]} | {run_kinds.get(kind, 0)} |")
    lines.append(f"| **total** | **{total}** | **{len(evaluated)}** |")
    lines.append("")

    lines.append("## Evaluated")
    lines.append("")
    lines.append("| Constraint | Kind | Level | Declared on | Target |")
    lines.append("|---|---|---|---|---|")
    for constraint in sorted(evaluated, key=_sort_key):
        lines.append(
            f"| `{constraint.identifier}` | {constraint.kind} | {constraint.level} | "
            f"`{constraint.context}` | `{constraint.target}` |"
        )
    lines.append("")

    lines.extend(_reads_an_unbuilt_index(metaschema))

    lines.append("## Not evaluated")
    lines.append("")
    lines.append(
        "Neither passed nor failed. A document that this tool reports no findings for "
        "may still violate any of these."
    )
    lines.append("")
    lines.append("| Constraint | Kind | Declared on | Why not |")
    lines.append("|---|---|---|---|")
    for constraint in sorted(metaschema.skipped(), key=_sort_key):
        identifier = constraint.identifier or "(unnamed)"
        lines.append(
            f"| `{identifier}` | {constraint.kind} | `{constraint.context or '-'}` | "
            f"{constraint.skipped} |"
        )
    lines.append("")
    return "\n".join(lines)


def _reads_an_unbuilt_index(metaschema: Metaschema) -> list[str]:
    """The evaluated constraints that can never reach a definite answer.

    An ``index-has-key`` is only as good as the ``index`` that fills the index
    it reads. Where that ``index`` constraint is one this tool skips, the
    lookup misses every key no matter what the document says, so the finding is
    always UNVERIFIABLE. Counting those among the evaluated constraints without
    saying so would overstate coverage, which is the one thing this file exists
    to prevent.
    """
    evaluated = metaschema.evaluated()
    built = {c.index_name for c in evaluated if c.kind == "index"}
    stranded = sorted(
        (c for c in evaluated if c.kind == "index-has-key" and c.index_name not in built),
        key=_sort_key,
    )
    lines = ["## Evaluated, but reading an index that is never built", ""]
    lines.append(
        "These constraints are parsed and run, and they can never produce a definite "
        "answer: the `index` constraint that would populate the index they read is one "
        "of the skipped constraints below, so every lookup misses. References checked "
        "against them are reported UNVERIFIABLE, naming the index, and are never "
        "reported as failures of the document."
    )
    lines.append("")
    lines.append("| Constraint | Declared on | Reads index | Populated by |")
    lines.append("|---|---|---|---|")
    for constraint in stranded:
        source = next(
            (
                c.identifier
                for c in metaschema.skipped()
                if c.kind == "index" and c.index_name == constraint.index_name
            ),
            "(nothing declares it)",
        )
        lines.append(
            f"| `{constraint.identifier}` | `{constraint.context}` | "
            f"`{constraint.index_name}` | `{source}`, skipped |"
        )
    lines.append("")
    return lines


def _sort_key(constraint: object) -> tuple[str, str, str]:
    return (
        getattr(constraint, "kind", ""),
        getattr(constraint, "identifier", ""),
        getattr(constraint, "target", ""),
    )


def main() -> int:
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/CONSTRAINT-COVERAGE.md")
    destination.write_text(render(), encoding="utf-8")
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
