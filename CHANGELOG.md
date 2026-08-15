# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
