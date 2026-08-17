# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- A scalar standing where the schema declares an assembly is now a
  `TYPE_MISMATCH` error. It was silently recorded as an untyped scalar, so
  everything below the substitution went unreachable and unreported: a catalog
  whose `metadata` was `null`, `42`, `true`, or a string exited 0 with no ERROR
  finding, and `{"catalog": null}` did the same for a document with no body at
  all. The walk now carries the shape the schema declares into the scalar case,
  including the 36 nodes that state `properties` without stating
  `"type": "object"`.
- `NonNegativeIntegerDatatype` and `PositiveIntegerDatatype` are each an
  `allOf` over a `$ref` to `IntegerDatatype` and a branch declaring
  `"type": "number"` with a `minimum`. The datatype index read only the branch,
  so both facets were lost: the base's narrower `integer` and the bound. A port
  range of `start: -1, end: 99.5` produced output byte for byte identical to
  `start: 443, end: 443`. Values below the bound are now
  `DATATYPE_BELOW_MINIMUM`, and a fractional value is a `TYPE_MISMATCH`.
- `__version__` said `0.1.0` while the package was `0.2.0`, so `--version` and
  the `tool.version` field on every JSON report named the wrong release of the
  rules that produced them. `tests/test_cli.py` now pins it to `pyproject.toml`.

### Added

- `ARRAY_TOO_SHORT`: the schema declares `"minItems": 1` on 409 arrays and none
  of them were evaluated, so an array present and empty read the same as one
  that conforms.
- Twelve gate-breaking tests for the above, each one failing before the fix,
  plus a control asserting a port range inside its bounds stays clean.

### Changed

- README: the status line said no release had been tagged, and the GitHub
  Action example said no release carried the action. `v0.1.0` and `v0.2.0` are
  both tagged and `v0.2.0` carries it. Nothing is on PyPI, which is unchanged.
- README "Limits": `minItems` and `minimum` moved out of the not-evaluated
  list, and the keywords absent from the vendored schema are now named as
  absent rather than listed as unevaluated.

## [0.2.0] - 2026-08-16

### Added

- `action.yml`: a composite GitHub Action that runs the CLI over a file, a
  directory, or a glob and annotates each finding on the file it came from.
  Inputs are `path`, `resolve`, and `fail-on`; counts are published as step
  outputs, including `unverifiable-count`. Nothing is installed and nothing is
  fetched: the package has no runtime dependencies, so the action runs the
  checked-out source off `PYTHONPATH`, and `actions/setup-python` is pinned to
  a commit SHA. The exit codes are the CLI's own, with two additions that
  refuse to pass silently: a `path` matching no file is exit 2, and an
  unreadable document is exit 2 even when every other document is clean.
  `tests/test_action_runner.py` and a CI self-test prove the gate fails on a
  catalog with a required property removed.

### Changed

- `test_every_action_is_pinned_to_a_full_commit_sha` now exempts a `uses: ./`
  reference to this repository's own action, which is checked out at the
  commit that runs it and has no SHA to pin. The exemption is not a hole: such
  a reference must resolve to an `action.yml` in this repository.

## [0.1.0] - 2026-08-16

### Fixed

- An `index-has-key` constraint whose index no evaluated `index` constraint
  builds no longer reports its references as unresolved. NIST populates two such
  indexes with constraints whose targets carry predicates outside the parsed
  Metapath subset, so the index is never built and every lookup missed; the
  references were reported as ERROR against documents that were correct. They
  are now UNVERIFIABLE and name the index. Measured effect on the 2026-08-15
  survey: 29 false ERRORs removed, every one verified by hand against the
  document first. The imports-withheld run is unaffected, so the 2026-08-14
  evidence stands unchanged.
- Both findings write-ups reported all eleven `CONSTRAINT_CARDINALITY` findings
  as ERROR. One is: the run recorded ten of them at WARNING, because they fire
  on `oscal-back-matter-resource-base64-rlink-cardinality`, which NIST declares
  at `level="WARNING"`. Their ERROR columns therefore summed to ten findings
  more than the runs recorded, against named organizations' documents. Both
  tables now give every code at the severity it was recorded at, and cover all
  twelve codes rather than eight, so the per-severity sums are the run's own.
  `tests/test_findings_evidence.py` had pinned the mistake in place by taking
  each count from the evidence and the word ERROR from nowhere; it now sums the
  table by severity and checks it against the recorded severity totals.
- `make sync` now runs `uv lock --check` before `uv sync --frozen`.
  `--frozen` installs from `uv.lock` without reading `pyproject.toml` and exits
  0 on a lock that no longer matches the manifest, so it was never the
  lockfile-drift gate it looked like. Measured on a scratch project with a
  deliberately stale lock.

### Added

- `docs/findings/2026-08-15-imports-supplied-survey.md` and its evidence JSON:
  the same 52 documents re-run with their imports located and supplied. 5,216 of
  the first run's 5,501 UNVERIFIABLE references resolved to something that
  exists, 178 resolved to nothing, and 107 still cannot be settled. All four
  FedRAMP rev 5 baselines went from 2,787 unanswerable control references to
  zero errors.
- `tools/survey.py` fetches the documents named in a target's `--resolve`
  column, in one pass before validation, recording their provenance separately
  under `supporting`. A supporting document is never counted as a surveyed
  document. Findings located inside one are named by its URL rather than by a
  cache path, so the evidence is reproducible on any machine.
- A generated "Evaluated, but reading an index that is never built" section in
  `docs/CONSTRAINT-COVERAGE.md`, and a break-the-gate test asserting the
  non-firing direction.
- `tests/test_findings_evidence.py` now recomputes both runs' headline numbers,
  and recomputes the delta table between them from the two evidence files rather
  than trusting it.
- Data cards under `docs/data/` for both ingest sources, and `docs/incidents/`
  with the postmortem convention. The README conformance table now covers all
  fifteen portfolio standards, states Observability as applying at the
  library/CLI tier rather than not at all, and names the gaps it has not closed.

- Initial version of the deterministic OSCAL structural validator: model
  detection across all eight OSCAL roots, a schema-guided document walk,
  datatype conformance from the schema's own declared patterns, document-wide
  UUID uniqueness, identifier reference resolution across a document's
  effective data model, and a rule citation with source URL and retrieval date
  on every finding, in both text and JSON output.
- Evaluation of NIST's published Metaschema constraint layer: `is-unique`,
  `index` uniqueness, `index-has-key` cross-references, and `has-cardinality`,
  read out of the vendored `*_metaschema_RESOLVED.xml` modules and reported at
  the severity NIST declares on each constraint. 78 of the 340 published
  constraints are evaluated; the other 262 are listed with reasons in
  `docs/CONSTRAINT-COVERAGE.md`, which is generated from the vendored files and
  guarded by a test.
- `--resolve`, which supplies imported catalogs and profiles from local files so
  that a reference can be answered definitely rather than reported UNVERIFIABLE.
  Nothing is ever fetched.
- Vendored, unmodified OSCAL 1.2.3 schema and metaschema snapshots with
  provenance and SHA-256 hashes recorded in
  `src/oscal_validate/vendor/SOURCES.md` and enforced by
  `tests/test_vendor_integrity.py`.
- Break-the-gate suite (`tests/test_break_the_gate.py`), byte-level determinism
  suite (`tests/test_determinism.py`), and a no-network suite
  (`tests/test_offline_guarantee.py`) that removes `socket` and runs the
  validator anyway.
- `docs/findings/2026-08-14-published-oscal-survey.md` and its evidence JSON:
  the validator run over 52 published OSCAL documents from NIST, FedRAMP, and
  four third-party publishers, with the survey harness (`tools/survey.py`) and
  target list committed so the run is reproducible. Thirteen carried at least
  one ERROR finding; every one was verified by hand before publication.
- Portfolio standards conformance kit: CI running the same `make verify` gate as
  local development, Semgrep and full-history TruffleHog scanning workflows,
  Dependabot updates, pre-commit hooks, CODEOWNERS, `SECURITY.md`,
  `CONTRIBUTING.md`, `CITATION.cff`, an ADR log under `docs/adr/`, an i18n
  declaration, responsible-tech audit notes, and a standards and metrics ledger
  (`docs/ROADMAP.md`).
