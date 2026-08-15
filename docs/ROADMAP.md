# Standards and metrics ledger

Last measured: 2026-08-14. Owner: Chelsea Kelly-Reif. Review cadence: per
release and quarterly.

This file is the enforcement ledger required by the portfolio Quality & Metrics
standard. A row is an AUTO-GATE, a concrete REVIEW-GATE with an evidence
artifact, or an explicit N/A with a reason, never an unowned aspiration. Feature
scope (what the tool deliberately does not check) lives in the README's "Limits"
section and in `docs/CONSTRAINT-COVERAGE.md`.

## Metrics

| Metric | Target | Measured by | Gate | Owner |
|---|---|---|---|---|
| Branch coverage | >= 90% | `make test` (pytest-cov; `fail_under = 90` in pyproject) | AUTO | Maintainer |
| Tests | 100% green on Python 3.12 | CI `verify` job (`make verify`) | AUTO | Maintainer |
| Lint / format / types | 0 errors | `make lint`, `make format`, `make typecheck` (`mypy --strict`) | AUTO | Maintainer |
| Cyclomatic complexity | <= 10 per function | ruff mccabe in `make lint` | AUTO | Maintainer |
| Determinism | Byte-identical output across runs and interpreter processes; no timestamp in any report | `tests/test_determinism.py` | AUTO | Maintainer |
| Vendored snapshot integrity | SHA-256 of every vendored file matches `vendor/SOURCES.md`, and no vendored file lacks a hash row | `tests/test_vendor_integrity.py` | AUTO | Maintainer |
| Gate self-test | Every seeded corruption of a clean document is caught | `tests/test_break_the_gate.py` | AUTO | Maintainer |
| The package stays offline | 0 sockets opened; 0 network imports anywhere under `src/` | `tests/test_offline_guarantee.py` | AUTO | Maintainer |
| Constraint coverage honesty | The published coverage table equals what the vendored files contain | `tests/test_constraint_coverage.py` | AUTO | Maintainer |
| Constraint inventory drift | The published constraint counts equal the vendored inventory | `tests/test_metaschema.py` | AUTO | Maintainer |
| Severity contract accuracy | UNVERIFIABLE never gates the exit code; ERROR always does | `tests/test_cli.py` plus release review of any severity change | AUTO + REVIEW | Maintainer |
| Findings match their evidence | Every headline number in `docs/findings/` is recomputed from the survey JSON | `tests/test_findings_evidence.py` | AUTO | Maintainer |
| robots.txt enforcement | A Disallow stops the fetch before the document is requested; an unreachable robots.txt stops it too; no override flag exists | `tests/test_survey_fetch.py` against a server on localhost | AUTO | Maintainer |
| Dependency vulnerabilities | 0 known in the locked toolchain | `make audit` (pip-audit) in verify and CI; Dependabot weekly | AUTO | Maintainer |
| Secret and SAST scanning | 0 verified secrets; 0 unresolved Semgrep findings | trufflehog.yml (push, PR, weekly), semgrep.yml (push, PR) | AUTO | Maintainer |
| SHA-pinned workflow actions | 100% | portfolio conformance checker; review on workflow diffs | AUTO | Maintainer |
| Spec snapshot freshness | Re-vendor and re-hash on a new OSCAL release | Manual check against the OSCAL releases page before a release | REVIEW | Maintainer |
| AI evaluation / GenAI telemetry | N/A: deterministic rule engine; no model, prompt, retrieval, embedding, or AI ranking path anywhere | Dependency and import scan (zero runtime deps) | N/A | Maintainer |

## Delivery health

For this unreleased library, deployment frequency and change lead time are the
applicable DORA signals once releases begin. Change-fail rate and recovery time
become meaningful only after a tagged release exists; they must remain N/A
rather than be filled with invented zeroes.

## Open review and owner actions

- Enable a branch protection ruleset on `main` (block force-push and deletion).
  This is a GitHub settings change; it cannot be made from inside the
  repository.
- Enable GitHub private vulnerability reporting in repository settings so the
  channel `SECURITY.md` prefers is actually on.
- Decide whether to cut a first tagged release and whether to publish to PyPI.
  Nothing is published anywhere today.
- Decide whether to widen the Metapath subset. Today 25 constraints are skipped
  purely because their targets carry predicates (`link[@rel='diagram' and
  starts-with(@href,'#')]` and similar), and a bounded predicate parser would
  reach most of them. It is a scope decision, not a code one. REVIEW, owner:
  maintainer.
- Decide whether to implement profile resolution. It would make `by-id` and
  `objective-id` references checkable and would let an SSP be checked against a
  resolved baseline rather than an unresolved profile. It is a large piece of
  the specification with its own test suite upstream. REVIEW, owner: maintainer.
- Re-run the survey against the same targets after the next OSCAL release, and
  record whether the findings persist.
