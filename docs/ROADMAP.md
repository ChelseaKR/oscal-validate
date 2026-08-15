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
| Findings match their evidence | Every headline number in `docs/findings/` is recomputed from the survey JSON, for both runs, including the delta between them | `tests/test_findings_evidence.py` | AUTO | Maintainer |
| Coverage honesty about stranded constraints | Every evaluated `index-has-key` whose index no evaluated `index` constraint builds is listed, and its references are reported UNVERIFIABLE rather than as failures | `tools/constraint_coverage.py` plus `tests/test_constraint_coverage.py` and `tests/test_break_the_gate.py` | AUTO | Maintainer |
| robots.txt enforcement | A Disallow stops the fetch before the document is requested; an unreachable robots.txt stops it too; no override flag exists | `tests/test_survey_fetch.py` against a server on localhost | AUTO | Maintainer |
| Dependency vulnerabilities | 0 known in the locked toolchain | `make audit` (pip-audit) in verify and CI; Dependabot weekly | AUTO | Maintainer |
| Lockfile agrees with the manifest | `uv.lock` resolves `pyproject.toml` as committed | `uv lock --check`, first step of `make sync`. Measured, not assumed: `uv sync --frozen` exits 0 on a drifted lock because it never reads `pyproject.toml`, so it cannot be this gate | AUTO | Maintainer |
| Secret and SAST scanning | 0 verified secrets; 0 unresolved Semgrep findings | trufflehog.yml (push, PR, weekly), semgrep.yml (push, PR) | AUTO | Maintainer |
| SHA-pinned workflow actions | 100% | portfolio conformance checker; review on workflow diffs | AUTO | Maintainer |
| Spec snapshot freshness | Re-vendor and re-hash on a new OSCAL release | Manual check against the OSCAL releases page before a release | REVIEW | Maintainer |
| AI evaluation / GenAI telemetry | N/A: deterministic rule engine; no model, prompt, retrieval, embedding, or AI ranking path anywhere | Dependency and import scan (zero runtime deps) | N/A | Maintainer |
| Performance | N/A: pure library/CLI with no hosted route and no shipped HTML, per PERFORMANCE-STANDARD section 0. There is no preview environment or frontend bundle to measure, and a perf job that cannot run against a real surface is declared N/A rather than wired in advisory mode | Reviewed on any change that adds a hosted route | N/A | Maintainer |
| Incident postmortems | Every incident gets a `docs/incidents/YYYY-MM-DD-<slug>.md` file in this repository. Zero incidents to date, which is a count and not an exemption | `docs/incidents/README.md`; the convention is exercised the first time it is needed | REVIEW | Maintainer |
| Data lineage | Every ingest source has a card in `docs/data/` naming the publisher, licence, retrieval date, refresh trigger, and tier | `docs/data/`; the vendored snapshot's hashes are additionally enforced by `tests/test_vendor_integrity.py` | REVIEW | Maintainer |

## Observability

Tier C, library/CLI, per OBSERVABILITY-STANDARD section 0. Distributed tracing,
SLOs, health probes, and RED metrics are out of scope: this is a single-shot
command with no network surface, no service, and nothing that outlives the
process. The report on stdout is the entire observable surface, and its
exit-code contract and `--format json` shape are asserted in
`tests/test_cli.py`.

The one control that is never tiered away is the no-secrets-in-logs gate, and
it holds here for a structural reason rather than a scanned one: this tool has
no logging framework and writes nothing anywhere except the report it was asked
for. Semgrep and ruff's `S` rules run over every push regardless.

`--log-format json` is the tier's opt-in structured-logging affordance. It is
not implemented. That is a gap and is listed below as one, not an exemption.

AI-DEV-MEASUREMENT: APPLIES. This repository was built with AI assistance,
disclosed in the README, so Track A delivery and quality-debt metrics are mined
portfolio-wide from git and PR history rather than computed here. Track B is
N/A: there is no model, prompt, or AI ranking path in the product, which is the
same fact the AI Evaluation row records.

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
- Register this repository in the portfolio's `applicability.yml`. It is public
  and it is absent from the manifest on `main`, which the manifest's own header
  calls a loud failure of the weekly conformance run. An entry exists on the
  unmerged branch `fix/applicability-manifest-drift`; until that lands, the
  conformance table above and in the README is the only record of scope.
- Create the `incident` and `sev1` through `sev4` labels. This is a GitHub
  settings change and cannot be made from inside the repository. Until it is
  made, the Incident Response row is honest about the gap rather than claiming
  the control.
- Record a per-record fetch timestamp in the survey evidence. The records carry
  the HTTP outcome and the resolved URL but date the fetch only at file level,
  which is short of what the data-governance lineage control asks for.
- Decide whether `--log-format json` is worth implementing, or whether the tier
  C affordance should be declared N/A with a reason. Today it is neither.
- Decide whether to add a release workflow or to declare releases N/A with a
  reason. "No release has been made yet" is a status, not a declaration.
