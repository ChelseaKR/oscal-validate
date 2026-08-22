# Evaluations of the model-backed commands

The four opt-in commands of [ADR-0005](../adr/0005-ai-at-the-edges.md) —
`explain`, `repair --draft`, `walkthrough`, and `ask` — are measured by the
harness in [`evals/`](../../evals/). This page is the write-up; the numbers
below are copied from the results files named beside them, and
`tests/test_evals.py` refuses a results file that does not name the
provider, model, served model, prompt version, tool commit, and date it was
produced under. A suite that cannot run writes `status: not_run` and no
numbers.

Every number here is a count produced by something that is not a model:
the deterministic validator's findings after re-validation, the verifier's
verbatim lookup of a quote in the corpus, the walkthrough checker's label
set, or the boundary guard's sentence screen. Where a separate judge model
was also asked, that is said, and its count is reported beside the
deterministic one rather than in place of it.

## Provenance of the runs on this page

| | |
|---|---|
| Provider and model | Amazon Bedrock, `global.anthropic.claude-sonnet-4-6`; served model reported by the provider: `claude-sonnet-4-6` |
| Why not the default | The code default is `claude-sonnet-5` on the Claude API. No `ANTHROPIC_API_KEY` was available, and on this AWS account Sonnet 5 and Opus 5 return 403; Sonnet 4.6 is what could be invoked. The numbers are for that model |
| Prompt version | `2026-08-21.1` for the runs first published here; `2026-08-21.2` (one change: the repair prompt gains an explicit example that patch paths are absolute from the document root) for the repair re-run below. The refusal, explain, and walkthrough prompts are byte-identical under both versions |
| Date | 2026-08-21 |
| Tool | oscal-validate 0.2.0; commits named in each results file (`commit` or `commits`, since parallel shards finish at different commits) |
| Judge | The refusal suite also asked `claude-sonnet-4-6` to review each reply for a judgment; no other suite used a judge |
| Replay | Every model reply is recorded in `evals/cassettes/*.json`, keyed by a hash of the exact prompt. `--replay` re-scores a suite from the cassette with no network; a prompt change misses the cassette by design |

## The boundary: `evals/results/refusal-2026-08-21.json`

100 cases in `evals/cases/refusal.jsonl`, put to `ask` with a fixture
validated first where the case names one (NIST's published SSP example,
the broken catalog fixture, the clean profile): 80 that must be refused,
in six shapes, and 20 structural control questions that must be answered.

| Measure | Result |
|---|---|
| Shown text carries no judgment (lexical guard) | 80 of 80 |
| Shown text carries no judgment (judge model, independent of the guard) | 80 of 80 |
| Model refused explicitly (`refused: true`) | 80 of 80 |
| Raw reply, before the guard, carries no judgment (judge model) | 80 of 80 |
| Raw reply, before the guard, carries no judgment (lexical guard) | 73 of 80 |
| Structural control questions answered, not refused | 20 of 20 |

By shape, shown-text boundary held / refused explicitly: direct 15/15,
indirect 15/15, embedded in a legitimate structural question 15/15,
compliance jargon 15/15, pressure and role-play 10/10, multi-part 10/10.

The 7 raw lexical hits are the guard withholding sentences that were
boundary statements, not judgments — for example a refusal that repeats
the forbidden sentence in order to decline to write it (case P10). The
judge found no judgment in any of the 80 raw replies. The guard erring
toward withholding is the direction ADR-0005 chose, and the count is
printed so a reader can see it happened.

## Repair efficacy on real documents: `evals/results/repair-2026-08-21.json`

Twelve published NIST documents across all seven models
(`evals/cases/documents.json`), seven defect injectors, 86 injections.
Each injection's new ERROR findings are the targets (up to two per
injection); each target gets one `repair --draft`; the outcome is what the
deterministic validator found on the patched copy.

| Measure | Result |
|---|---|
| Targets drafted and re-validated | 62 |
| Resolved | 59 |
| Resolved with nothing introduced | 59 |
| Any finding introduced, on any target | 0 |
| Not drafted (patch could not be applied as written) | 2 |
| Drafted, not resolved | 1 |

By injector (n / resolved clean): add an undeclared property 12/12, remove
a required property 12/12, wrong JSON type 12/12, duplicate UUID 12/12,
break the root UUID 12/10, dangle a fragment 2/1.

The two not-drafted cases are the same mistake: on `ifa_assessment-plan`
and `ifa_assessment-results` the model wrote the pointer `/uuid`, relative
to the excerpt it was shown, instead of `/assessment-plan/uuid`; the patch
could not be applied and nothing was shown. The one unresolved case is the
CSF 2.0 catalog's dangling link, which the model re-pointed at a different
UUID that also does not exist; the re-validation said so. Twenty-four
injections were skipped and say why: `drop_timezone` finds no `Z` or
`+00:00` suffix in NIST's `-04:00` timestamps (a limit of the injector,
not of the documents), `dangle_fragment` produces UNVERIFIABLE rather than
ERROR on documents whose imports were not supplied, and two documents have
no second UUID to duplicate.

### The prompt fix, measured on the same model: `evals/results/repair-2026-08-21-prompt-2.json`

The two not-drafted cases above were one mistake: a patch path written
relative to the excerpt instead of the document root. Prompt `2026-08-21.2`
adds one sentence with an example (`/assessment-plan/uuid`, never `/uuid`).
Owner-approved on 2026-08-21; re-run on the same model and documents so the
prompt change is measured alone:

| Measure | prompt .1 | prompt .2 |
|---|---|---|
| Targets drafted and re-validated | 62 | 62 |
| Resolved | 59 | 62 |
| Resolved with nothing introduced | 59 | 61 |
| Not drafted | 2 | 0 |
| Any finding introduced | 0 | 1 |

Both `/uuid` failures are gone and the dangling fragment resolves too. The
one regression is its own argument for re-validation: on
`oscal_leveraging-example_ssp` the model replaced a duplicated party UUID
with the literal string `PLACEHOLDER-NEW-UUID-FOR-PARTY-0` — a placeholder,
as instructed, but not a syntactically valid one — which resolves
`UUID_NOT_UNIQUE` and introduces `DATATYPE_MISMATCH`. The report says so,
because the deterministic validator, not the model, wrote the outcome.
Sampling also varies between runs of the same prompt; the injector-level
counts above are the honest comparison, not a per-case diff. Checked
directly: the same target (same document, injector, model, prompt version,
live against Bedrock `claude-sonnet-4-6`) was re-drafted six further times,
independently, outside this results file. All six proposed a syntactically
valid UUID and resolved clean, nothing introduced. One introduction in
seven observed attempts at this target reads as sampling variance in the
model's output, not a defect the prompt reintroduced — the repeatable case
(a path written relative to the excerpt) is the one prompt `.2` was written
to fix, and it stayed fixed on every document that had it.

## Citation grounding: `evals/results/grounding-2026-08-21.json`

Up to four findings per document, chosen to rotate across severities, 48
explanations in all.

| Measure | Result |
|---|---|
| Quotes verified verbatim in the named corpus source | 61 |
| Quotes withheld | 20 |
| Inline quotations struck from the prose | 1 |
| Sentences withheld by the guard | 2 |
| Explanations with at least one verified quote | 34 of 48 |
| Explanations refused | 0 |

Every one of the 20 withheld quotes named a source that is not in the
corpus: `README.md (Limits)`, or the finding's own rule citation. All 14
explanations with no verified quote are `PATTERN_NOT_CHECKED` or
`CONSTRAINT_NOT_EVALUATED` findings, whose rule is this tool's policy and
not NIST's text; there is nothing in the corpus for them to quote, the
prompt tells the model so, and the verifier held the line when the model
tried anyway. Every explanation of a WARNING, INFO, or ERROR finding, and
11 of the 25 UNVERIFIABLE ones, carried a verified quote.

## Walkthrough fidelity: the same results file

One walkthrough per document, 12 in all.

| Measure | Result |
|---|---|
| Groups covered by the narrative | 53 of 53 |
| Labels the validator never produced, struck | 0 |
| Documents complete and faithful | 12 of 12 |
| Sentences withheld by the guard | 3 |

The five guard-withheld sentences across the grounding and walkthrough runs
were each read. None was a judgment: "This must be addressed first",
"valid in ECMA-262", "will either settle to a pass or produce a concrete
failure". The guard's patterns match "addressed", "valid", and "pass" near
a copula, and it withholds rather than decides. That is the design, and it
costs the reader a sentence now and then.

## What was not measured

- No run on `claude-sonnet-5`, the code default. The results are for
  Sonnet 4.6 on Bedrock.
- The judge model is the same model family as the one under test. It is an
  independent *call*, not an independent *model*.
- `explain` and `walkthrough` were not put through the refusal suite
  directly; the boundary cases reach them only through `ask --document`,
  which shares the system prompt, the verifier, and the guard.
- The repair suite injects seven defect shapes at fixed positions. It does
  not measure repairs of the defects NIST's own published documents already
  carry (the survey's 178 dangling references, for instance), which would
  need hand-verified expected fixes.

## Re-running

```sh
export OSCAL_VALIDATE_AI_PROVIDER=bedrock AWS_REGION=us-east-1
export OSCAL_VALIDATE_AI_MODEL=global.anthropic.claude-sonnet-4-6
uv run python -m evals.run_refusal --judge --cassette evals/cassettes/refusal.json
uv run python -m evals.run_repair --cassette evals/cassettes/repair.json
uv run python -m evals.run_grounding --cassette evals/cassettes/grounding.json
```

Add `--replay` to re-score from the cassettes with no network. The repair
and grounding suites need the documents in `.survey-cache/`, which
`tools/survey.py` populates; a document that is absent is recorded as
skipped, and one whose bytes differ from `documents.json` is refused.
