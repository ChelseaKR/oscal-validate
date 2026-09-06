# Standards and metrics ledger

Last measured: 2026-08-21. Owner: Chelsea Kelly-Reif. Review cadence: per
release and quarterly.

This file is the enforcement ledger required by the portfolio Quality & Metrics
standard. A row is an AUTO-GATE, a concrete REVIEW-GATE with an evidence
artifact, or an explicit N/A with a reason, never an unowned aspiration. Feature
scope (what the tool deliberately does not check) lives in the README's "Limits"
section and in `docs/CONSTRAINT-COVERAGE.md`. Where that scope is intended to
move, and in what order, is [`docs/EXPANSION-PLAN.md`](EXPANSION-PLAN.md); the
owner actions listed at the end of this file are carried there as its Phase 7,
so that a decision waiting on a person is not filed as work waiting on time.

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
| The validator stays offline | 0 sockets opened by the default command; 0 network imports under `src/` outside `oscal_validate/ai/`; nothing outside `ai/` imports it; `ai/` imports the SDK only inside a function | `tests/test_offline_guarantee.py` | AUTO | Maintainer |
| Default path byte identity | The default command's stdout and exit code over the fixtures and nine published NIST documents equal the goldens first captured from commit `6978895`, the last before ADR-0005, and recaptured once on 2026-08-29 from the same documents when a false sentence in the report was corrected (README, Limits); a validation run in a fresh process loads neither `oscal_validate.ai` nor the SDK | `tests/test_default_path_byte_identity.py` | AUTO | Maintainer |
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
| Boundary: no implementation, security, or authorization judgment shown | 80 of 80 refuse-cases hold by both the lexical guard and an independent judge call; 20 of 20 structural controls answered. Last live run 2026-08-21 on Bedrock `claude-sonnet-4-6`: 80/80, 80/80, 20/20 | `evals/run_refusal.py` over `evals/cases/refusal.jsonl`; results in `evals/results/`; provenance enforced by `tests/test_evals.py` | REVIEW (live run per prompt change; replay from cassette is AUTO-checkable) | Maintainer |
| Repair drafts verified by re-validation | Every draft shown was re-validated by the deterministic validator; the eval reports resolved / clean / introduced / not drafted. Last run: 59 of 62 resolved, 0 introduced | `evals/run_repair.py` over `evals/cases/documents.json` | REVIEW | Maintainer |
| Citation grounding | Every quote shown was found verbatim in the named corpus source; withheld quotes are counted, never shown. Last run: 61 verified, 20 withheld, all withheld ones naming a non-corpus source | `oscal_validate.ai.verify` at run time; `evals/run_grounding.py` | AUTO at run time + REVIEW | Maintainer |
| Walkthrough fidelity | No label the validator did not produce is shown; no group is omitted. Last run: 53 of 53 groups covered, 0 struck | `oscal_validate.ai.walkthrough.check` at run time; `evals/run_grounding.py` | AUTO at run time + REVIEW | Maintainer |
| Corpus integrity | SHA-256 of every corpus text matches `ai/corpus/MANIFEST.json`; the prose rules `rules.py` quotes verify against it | `tests/test_ai_sources.py` | AUTO | Maintainer |
| Eval provenance | Every results file names provider, model, served model, prompt version, commit, and date, or is `not_run` with a reason and no numbers | `tests/test_evals.py` | AUTO | Maintainer |
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
portfolio-wide from git and PR history rather than computed here. Track B
applies since ADR-0005 to the four opt-in model-backed commands, and is served
by the boundary, repair, grounding, and walkthrough rows above; the validator
itself still has no model, prompt, or AI ranking path.

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
- ~~Decide whether to widen the Metapath subset.~~ Decided and done 2026-08-19
  (ADR-0004): a bounded predicate and path grammar, enumerated from the
  vendored files, reaches 24 of the 25 — coverage is 102 of 340 and the
  regenerated `docs/CONSTRAINT-COVERAGE.md` carries the split. The one
  survivor is `oscal-ssp-by-component-uuid-index`, whose target dereferences a
  second document through `doc()`; implementing `doc()` is a separate decision
  that stays open. Measured on the widened corpus before any new document was
  supplied: the 24 found zero new violations and settled 108 previously
  unverifiable references through newly buildable indexes
  (`docs/findings/2026-08-19-constraints-reached-survey.md`). REVIEW closed;
  the `doc()` decision remains with the maintainer.
- Decide whether to implement profile resolution. It would make `by-id` and
  `objective-id` references checkable and would let an SSP be checked against a
  resolved baseline rather than an unresolved profile. It is a large piece of
  the specification with its own test suite upstream. REVIEW, owner: maintainer.
- Re-run the survey against the same targets after the next OSCAL release, and
  record whether the findings persist.
- ~~Decide what to do about `/mapping-collection/mappings`, which no rule in
  this tool reads.~~ Decided and done 2026-08-27 (ADR-0007). The blocker was
  one shape, enumerated from the vendored schema: `mappings` is the only node a
  document can reach that the resolver declined, and it is declined because it
  is the only `group-as` of 394 in the vendored metaschema modules without
  `in-json="ARRAY"`. Resolving "one X or an array of X", and only that,
  reads the model: `tests/test_break_the_gate.py` now seeds seven corruptions
  inside a mapping, every one of which produced 0 ERROR before, and the seven
  published mapping collections report no `SUBTREE_NOT_READ` and 31 ERROR
  findings where they reported none. REVIEW closed.
- Decide how a document that declares an older `oscal-version` should be
  reported. Everything is validated against the vendored 1.2.3 schema and
  `OSCAL_VERSION_DIFFERS` warns about the gap, which was sufficient while every
  ERROR in the corpus was version-independent. The 2026-08-19 run produced the
  first ERRORs that turn on the difference: three mapping collections declare a
  release that has no mapping model at all, and one component definition declares
  a pre-1.0 release candidate whose schema NIST does not publish standalone.
  Checking each finding against its document's declared version is currently a
  manual step in the write-up. REVIEW, owner: maintainer.
- Register this repository in the portfolio's `applicability.yml`. It is public
  and it is absent from the manifest on `main`, which the manifest's own header
  calls a loud failure of the weekly conformance run. An entry exists on the
  unmerged branch `fix/applicability-manifest-drift`; until that lands, the
  conformance table above and in the README is the only record of scope.
- ~~Create the `incident` and `sev1` through `sev4` labels.~~ Done 2026-09-05.
  The five labels exist, and each `sevN` carries a description saying what it
  means *for this project* rather than a generic severity word: sev1 is a
  published wrong verdict, sev2 is a gate that cannot fail or a claim the code
  contradicts, sev3 is degraded output with bounded blast radius, sev4 is
  cosmetic. The Incident Response row now claims the control rather than
  recording the gap. The convention itself is still unexercised, which is a
  count and not an exemption.
- ~~Record a per-record fetch timestamp in the survey evidence.~~ Done
  2026-09-05. `tools/fetch.py` stamps every `FetchResult` with `fetched_at` —
  UTC, RFC 3339, whole seconds, taken once the response body has arrived — and
  `tools/survey.py` writes it into the record's `fetch` block and carries it
  forward under `--provenance` rather than restamping a cached read with the
  present. `tests/test_survey_fetch.py` holds both: the date is bracketed
  against the clock, and a cache-only record is asserted to carry no date at
  all. The five surveys already under `docs/findings/` were run before the
  field existed and are not backfilled, so their lineage is still dated at
  file level; the data card says so rather than implying otherwise.
- Decide whether `--log-format json` is worth implementing, or whether the tier
  C affordance should be declared N/A with a reason. Today it is neither.
- Decide whether to add a release workflow or to declare releases N/A with a
  reason. "No release has been made yet" is a status, not a declaration.
- Decide whether to re-record the grounding eval corpus. **The false sentence
  is gone as of 2026-08-29, and `tests/cassettes/walkthrough-nist-ssp.json` was
  re-recorded the same day; this entry is now only about the eval corpus.** The
  report's per-kind `CONSTRAINT_NOT_EVALUATED` sentence for `allowed-values`
  said "most allowed-value sets declare allow-other, so a value outside them is
  not necessarily a violation", where 60 of 200 declare it and the Metaschema
  specification makes the absent attribute mean the set is closed. It now
  states the applicable-set reason that the per-constraint reasons and the
  README's Limits section already gave, and
  `tests/test_metaschema.py::test_the_allowed_values_summary_claims_nothing_the_vendored_files_contradict`
  measures the 60/140 split off the vendored files and fails if a frequency
  claim they contradict returns. The 24 files in `tests/golden/` were
  recaptured offline in the same change. REVIEW, owner: maintainer.

  **What is left is a live billed call on the owner's Bedrock account**, which
  is why it is an owner action and not a code change:

  | Corpus | State | In `make verify`? |
  |---|---|---|
  | `tests/cassettes/walkthrough-nist-ssp.json` | **re-recorded 2026-08-29** on `global.anthropic.claude-sonnet-4-6`, 1,424 in / 1,710 out; declaration removed and the replay test runs again | yes, and it fails closed |
  | `evals/cassettes/grounding.json` | partly orphaned; replay measured 2026-08-29 at 12 walkthrough documents to 0, and grounded explanations 34 to 6 | no: `testpaths = ["tests"]` |
  | `evals/cassettes/repair.json`, `evals/cassettes/refusal.json` | untouched, those prompts never carried the sentence | no |

  The fail-closed path is unchanged by the re-record and was re-checked against
  the new cassette on 2026-08-29: a cassette that cannot answer the prompt makes
  the command report `walkthrough NOT EVALUATED` and exit 2 in both formats, a
  stale cassette that is not declared fails the suite, a declaration that
  outlives its staleness fails, and the declared deadline expiring fails. The
  one thing that cannot happen is the recording quietly replaying an answer to
  a question the tool no longer asks.

  The prompt is no longer built from the report's prose, so this class of
  obligation does not recur: a copy edit to a report sentence now leaves the
  prompt byte-identical, proven by
  `tests/test_ai_prompt_decoupling.py`. Two couplings of the same kind remain
  and were deliberately left, because fixing them spends re-records rather than
  saving them, and the choice is the owner's: `ai/sources.py` still selects NIST
  passages by keyword-matching `finding.message`, which is what orphans the
  grounding explanations above and would orphan `explain-broken-catalog.json`
  and `repair-broken-catalog.json` if changed (measured: both fail); and
  `explain`, `repair` and `ask` still exit 0 when the model cannot be reached,
  where `walkthrough` now exits 2.
