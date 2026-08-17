<!--
Thanks for a PR. CONTRIBUTING.md has the local gate: `uv sync --locked`, then
`make verify`, which runs exactly what CI runs. Delete any section that does not
apply; most PRs are not a new rule.
-->

## What and why

<!-- What changed, and why. Link an issue if one exists. -->

## Checks

- [ ] `make verify` passes locally (ruff lint, ruff format, mypy --strict,
      pytest with branch coverage >= 90%, pip-audit)
- [ ] `CHANGELOG.md` updated under `[Unreleased]` if behaviour changed

### If this adds or changes a check

- [ ] A break-the-gate case in `tests/test_break_the_gate.py`: a document that
      fails without the change and passes with it
- [ ] The finding cites a real, quotable line from a vendored NIST file or a
      NIST documentation page, with the date it was retrieved. A rule this tool
      cannot cite is a rule it should not enforce.
- [ ] Severity is justified: `ERROR` only where the published rule is
      unambiguous and the documents in hand can settle it, `UNVERIFIABLE`
      rather than a guess where they cannot
- [ ] Nothing that was previously reported as UNVERIFIABLE has become silent

### If this touches the vendored files

- [ ] `src/oscal_validate/vendor/SOURCES.md` hashes and dates updated
- [ ] `make coverage-doc` re-run and `docs/CONSTRAINT-COVERAGE.md` committed
