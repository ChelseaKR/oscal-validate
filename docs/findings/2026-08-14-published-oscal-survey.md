# What 52 published OSCAL documents actually say

Survey run 2026-08-14 with `oscal-validate` at commit-time `main`, against
NIST's OSCAL 1.2.3 schema and constraint layer. Evidence:
[`2026-08-14-published-oscal-survey.json`](2026-08-14-published-oscal-survey.json),
written by [`tools/survey.py`](../../tools/survey.py) from the target list in
[`tools/survey-urls.txt`](../../tools/survey-urls.txt).

The tool was built first and pointed at reality second. This is what came back.

**What this is not.** Nothing below says anything about whether any control is
implemented, whether any system is secure, or whether any package would be
authorized. Every finding is about whether a published document conforms to the
published specification. That is a much smaller question, and it is the only
one this tool can answer.

**Nor is it a report on anyone's software.** Every finding here describes a
document as published on 2026-08-14 and its conformance to the specification as
published on the same date. None of it is a claim about the tools that produced
those documents. No issue or pull request was filed anywhere on the strength of
this survey, and this project is not affiliated with, endorsed by, or reviewed
by NIST, FedRAMP, or StateRAMP.

## Headline

| | count | of documents validated |
|---|---:|---:|
| Documents attempted | 52 | |
| Documents validated | 52 | 100% |
| Blocked by robots.txt | 0 | 0% |
| Carried at least one ERROR finding | 13 | 25% |
| Had a complete effective data model (every import supplied) | 22 | 42% |
| Of those 22, carried at least one ERROR | 6 | 27% |

26.1 MB of OSCAL across seven of the eight models: 13 catalogs, 12 profiles, 9
system security plans, 6 component definitions, 4 assessment plans, 4
assessment results, 4 plans of action and milestones. No `mapping-collection`
document was in the sample.

Finding totals across the whole sample, by the severity each finding was
actually recorded at. A constraint finding carries the severity NIST declares
on the constraint, so one code can appear at two severities and
`CONSTRAINT_CARDINALITY` does:

| Code | Severity | Count |
|---|---|---:|
| `REFERENCE_UNRESOLVED` | ERROR | 568 |
| `UUID_NOT_UNIQUE` | ERROR | 427 |
| `TYPE_MISMATCH` | ERROR | 8 |
| `DATATYPE_MISMATCH` | ERROR | 6 |
| `CONSTRAINT_NOT_UNIQUE` | ERROR | 2 |
| `CONSTRAINT_CARDINALITY` | ERROR | 1 |
| `OSCAL_VERSION_DIFFERS` | WARNING | 52 |
| `CONSTRAINT_CARDINALITY` | WARNING | 10 |
| `REFERENCE_UNVERIFIABLE` | UNVERIFIABLE | 5,501 |
| `CONSTRAINT_NOT_EVALUATED` | UNVERIFIABLE | 312 |
| `PATTERN_NOT_CHECKED` | UNVERIFIABLE | 50 |
| `IMPORT_NOT_SUPPLIED` | INFO | 93 |
| `IMPORT_RESOLVED` | INFO | 7 |

1,012 ERROR, 62 WARNING, 5,863 UNVERIFIABLE and 100 INFO, which is every
finding the run recorded. The ten `CONSTRAINT_CARDINALITY` warnings are all
`oscal-back-matter-resource-base64-rlink-cardinality`, which NIST declares at
`level="WARNING"`; the one error is
`oscal-implemented-requirement-by-component-cardinality`, which declares no
level and so takes the default.

`REFERENCE_UNVERIFIABLE` and `IMPORT_NOT_SUPPLIED` are the important pair and
are discussed under
[Finding 5](#finding-5-most-of-what-a-validator-sees-it-cannot-settle).

## Method, and what it can and cannot support

**The sample is purposive, not random.** It is every OSCAL JSON example NIST
publishes in `usnistgov/oscal-content`, NIST's own control catalogs and
SP 800-53 baselines, the FedRAMP baselines and templates as they are reachable
today, and a spread of third-party publishers. It was chosen to cover as many
models and publishers as possible, not to represent any population. **No
percentage here is a population estimate**, and the denominator changes meaning
between groups: NIST's `examples/` directory is deliberately small and
illustrative, and a template is not a filled-in package.

| Group | Documents | Publisher |
|---|---:|---|
| `nist-example` | 18 | `usnistgov/oscal-content`, `examples/` |
| `nist-catalog` | 6 | `usnistgov/oscal-content`, control catalogs |
| `nist-baseline` | 6 | `usnistgov/oscal-content`, SP 800-53 baselines |
| `fedramp` | 9 | `OSCAL-Foundation/fedramp-automation`, `OSCAL-Foundation/fedramp-resources` |
| `vendor` | 13 | AWS Labs, EasyDynamics, ComplianceAsCode, IBM |

**On the FedRAMP sources.** `GSA/fedramp-automation`, where the FedRAMP OSCAL
baselines and templates were published, was archived in July 2025 and has since
been removed from GitHub; it returns HTTP 404, and `automate.fedramp.gov` no
longer resolves in DNS. The two repositories used here are the reachable copies
as of 2026-08-14; the first is a fork carrying the original commit history.
Neither states a license. Findings about them are findings about those files as
published there, on that date, and nothing more.

**Everything was fetched once, politely.** `robots.txt` first, an identifying
User-Agent naming the tool and linking to its repository, a two-second minimum
interval per host, one request per document. `raw.githubusercontent.com`
publishes no `robots.txt`, which [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309)
section 2.3.1.3 treats as permission to proceed; nothing in the sample
disallowed this tool, so nothing had to be skipped. The posture is in
[`tools/fetch.py`](../../tools/fetch.py) and is tested against a server on
localhost.

**Only metadata and findings were recorded.** The evidence JSON holds the HTTP
outcome, the model, the byte count, how many imports were supplied, the finding
codes with their counts, and one JSON Pointer per code. No value read from any
document is stored in this repository. A findings file full of other people's
system descriptions would be both unnecessary and rude.

**Every ERROR quoted below was verified by hand** against the document it came
from, independently of the tool that reported it. Where the check was
inconclusive, it is reported as UNVERIFIABLE and is not counted as a defect.

## Finding 1: a link in NIST SP 800-53 rev 5 names a control statement that does not exist

In `NIST_SP-800-53_rev5_catalog.json`, control `sa-24` carries ten assessment
objectives, each with an `assessment-for` link back to the statement it
assesses. Four point at `#sa-24_smt.a.1` through `#sa-24_smt.a.4`. One points
at a statement that does not exist:

```
ERROR  REFERENCE_UNRESOLVED  at=/catalog/groups/16/controls/23/parts/2/parts/0/parts/4/links/0/href
    href = #ac-2_smt.a.5
```

The objective is `sa-24_obj.a-5`, and `sa-24_smt.a.5` exists in the same
control. The string `ac-2_smt.a.5` occurs exactly once in the whole 10 MB
document, in that href, and no object anywhere in the catalog carries it as an
`id`.

A catalog imports nothing, so its effective data model is itself, and by the
published rule the fragment has to resolve inside it:

> "This approach uses a relative reference consisting of only a URI fragment
> containing the identifier or UUID of the referenced object within the current
> documents effective data model."
> — NIST, [URI Usage](https://pages.nist.gov/OSCAL/learn/concepts/uri-use/),
> page last updated 2025-03-03, retrieved 2026-08-14

**And the tool cannot see the rest of it.** The remaining five of the ten
objectives link to `#ac-2_smt.b`, which is a real statement — of control
`ac-2`, not `sa-24`, whose own `sa-24_smt.b` exists. Those five references
resolve, so a resolution check passes them in silence. One dangling reference is
reported; five references into a different control are not. That is a limit of
what reference resolution can be, not an omission: a checker can tell you an
identifier is absent, and it cannot tell you a present identifier is the wrong
one.

## Finding 2: 64 dangling fragments in SP 800-171 rev 3, all of one shape

`NIST_SP800-171_rev3_catalog.json` makes 781 fragment references. 359 name a
back-matter resource by UUID and resolve. 358 name an `SR-` identifier and
resolve. 64 name an `SR-` identifier and do not.

Every one of the 64 has the same shape. They reference an `SR-` identifier at
the control level, such as `#SR-03.01.02`, and the document declares `SR-`
identifiers only at the item level below it: `SR-03.01.01.a`, `SR-03.01.01.c`,
`SR-03.01.01.c.02`, and so on. Nothing in the catalog carries a bare
`SR-03.xx.yy` as an `id`. There are 29 distinct such targets, referenced 64
times.

This is one convention applied inconsistently, not 64 independent mistakes, and
telling those two apart is most of what a structural check over a whole document
is good for.

## Finding 3: a resolved baseline keeps 501 links to controls it no longer contains

`NIST_SP-800-53_rev5_LOW-baseline-resolved-profile_catalog.json` is a catalog,
so it imports nothing and its fragments must resolve within it. 501 do not.
`#pm-9` alone appears 27 times; the LOW baseline contains no control `pm-9`.

The pattern is consistent: these are `related` and `reference` links from
controls that *are* in the baseline to controls that are *not*. A resolved
baseline is a smaller catalog than the one it came from, and the links its
controls carry were written against the larger one.

Whether a resolved profile ought to prune such links is a question for the
profile-resolution specification, not for this tool. What is checkable, and
what is reported here, is that the document as published contains 501 fragment
references that resolve to nothing inside it.

## Finding 4: identifier reuse, in NIST content and in FedRAMP templates

OSCAL is unambiguous that a UUID identifies exactly one thing:

> "OSCAL's machine-oriented UUID identifiers are always globally-unique."
> — NIST, [Identifier Use and UUIDs](https://pages.nist.gov/OSCAL/learn/concepts/identifier-use/),
> page last updated 2025-06-10, retrieved 2026-08-14

427 reused UUIDs turned up, concentrated in four documents:

- **`NIST_CSF_v2.0_catalog.json`**: the catalog's own `uuid`
  (`720a010b-…0966f5`) is also the `uuid` of a back-matter resource. A `#`
  reference to that value cannot say which of the two it means.
- **`fedramp-ssp-example_NORMALIZED_.oscal.json`**: 408 reuses. The document
  uses structured placeholder UUIDs of the form `11111111-2222-4000-8000-…`,
  and the same value identifies an `implemented-requirement` and a statement
  inside it. This is an example file, and placeholder identifiers are what an
  example file is for; it is reported because the tool has no way to tell a
  deliberate placeholder from an accidental copy, and inventing one would be
  the first step toward passing real duplicates.
- **`FedRAMP-SAR-OSCAL-Template.json`** (9) and
  **`FedRAMP-SAP-OSCAL-Template.json`** (3): consecutive steps of one activity
  sharing a `uuid`, and back-matter resources sharing a `uuid`.
- Two component definitions (NIST's own example and EasyDynamics' sample, which
  is derived from it) reuse one UUID between an implemented requirement and its
  statement.

NIST's published constraint layer indexes UUIDs in particular places and
declares no constraint that a UUID is unique across a document as a whole. This
check comes from the prose rule instead, which is why it is worth having.

## Finding 5: most of what a validator sees, it cannot settle

5,501 UNVERIFIABLE reference findings against 568 ERRORs. The ratio is the
finding.

An SSP names controls defined in a profile, which names controls defined in a
catalog. Hand the validator only the SSP and it can say nothing about any of
those references, because OSCAL identifiers are explicitly cross-instance
scoped and the answer may be in a document it was not given. 93 imports across
the sample named a document that was not supplied.

The alternative is a tool that fetches what it is missing, and then a clean run
depends on whatever a URL served that morning. This tool takes the other side:
supply the imported documents with `--resolve` and get a definite answer, or
get UNVERIFIABLE and know exactly why.

The difference is measurable here. With every import supplied, the four
SP 800-53 rev 5 baseline profiles resolve **every** `with-id` against the rev 5
catalog, across LOW, MODERATE, HIGH and PRIVACY: no dangling control reference
in any of them. That is a real, positive result about NIST's baselines, and it
is only available because the catalog was handed over. Run the same profile
alone and the tool reports several hundred references it cannot judge.

## Finding 6: two published documents disagree with the schema on JSON types

`fedramp-ssp-example_NORMALIZED_.oscal.json` gives `port-range/start` and
`port-range/end` as JSON strings (`"start": "443"`). The schema declares them
`PositiveIntegerDatatype`, which is `"type": "integer"`. Eight occurrences.

Four controls in ComplianceAsCode's HIPAA catalog carry `"title": ""`. The
schema declares `title` as `MarkupLineDatatype`, whose pattern `^[^\n]+$`
requires at least one character. Two FedRAMP templates carry an empty `title`
on a role and on a remediation for the same reason.

These are the findings an ordinary JSON Schema validator would also produce.
They are listed for completeness, and because six of them across 52 documents
is a useful calibration: the schema layer is not where published OSCAL goes
wrong.

## Finding 7: the constraint layer catches things the schema cannot, and it is small

Two `is-unique` violations and eleven `has-cardinality` violations came from
NIST's own constraint files, at NIST's own declared severity. The two
uniqueness ones are duplicate `responsible-party` role assignments in a FedRAMP
template and a duplicate property key in another.

More interesting is what was *not* available to catch. Of the 340 constraints
NIST publishes across the OSCAL 1.2.3 metaschema modules, this tool evaluates
78. The other 262 are listed, with reasons, in
[`docs/CONSTRAINT-COVERAGE.md`](../CONSTRAINT-COVERAGE.md): 200 are
`allowed-values` sets that mostly permit other values, 25 are `matches`, 12 are
`expect` tests written in Metapath, and 25 have target expressions outside the
Metapath subset this tool parses.

And the assessment models publish no referential integrity at all. The
`oscal_assessment-common`, `oscal_assessment-results` and `oscal_poam` modules
declare zero `index` and zero `index-has-key` constraints, so there is no
published rule tying a finding's `observation-uuid` to an observation that
exists. This tool therefore does not check it. That gap is in the
specification, not in this implementation, and filling it here would mean
inventing a rule and citing myself for it.

## Every document that carried an ERROR

Paths are relative to each repository. "Complete" means every document named by
an import was supplied to the run.

| Document | Model | Complete | ERROR findings |
|---|---|---|---|
| `examples/component-definition/json/example-component-definition.json` | component-definition | no | `UUID_NOT_UNIQUE` x1 |
| `nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json` | catalog | yes | `REFERENCE_UNRESOLVED` x1 |
| `nist.gov/CSF/v2.0/json/NIST_CSF_v2.0_catalog.json` | catalog | yes | `UUID_NOT_UNIQUE` x1 |
| `nist.gov/SP800-171/rev3/json/NIST_SP800-171_rev3_catalog.json` | catalog | yes | `REFERENCE_UNRESOLVED` x64 |
| `nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_LOW-baseline-resolved-profile_catalog.json` | catalog | yes | `REFERENCE_UNRESOLVED` x501 |
| `nist.gov/SP800-53/rev4/json/NIST_SP-800-53_rev4_MODERATE-baseline_profile.json` | profile | yes | `REFERENCE_UNRESOLVED` x2 |
| `dist/content/rev5/templates/ssp/json/FedRAMP-SSP-OSCAL-Template.json` | system-security-plan | no | `CONSTRAINT_CARDINALITY` x1; `CONSTRAINT_NOT_UNIQUE` x1; `UUID_NOT_UNIQUE` x4 |
| `dist/content/rev5/templates/sap/json/FedRAMP-SAP-OSCAL-Template.json` | assessment-plan | no | `CONSTRAINT_CARDINALITY` x2; `CONSTRAINT_NOT_UNIQUE` x1; `DATATYPE_MISMATCH` x1; `UUID_NOT_UNIQUE` x3 |
| `dist/content/rev5/templates/sar/json/FedRAMP-SAR-OSCAL-Template.json` | assessment-results | no | `CONSTRAINT_CARDINALITY` x1; `DATATYPE_MISMATCH` x1; `UUID_NOT_UNIQUE` x9 |
| `examples/ssp/json/fedramp-ssp-example_NORMALIZED_.oscal.json` | system-security-plan | no | `TYPE_MISMATCH` x8; `UUID_NOT_UNIQUE` x408 |
| `samples/component-definition-example.json` | component-definition | no | `UUID_NOT_UNIQUE` x1 |
| `catalogs/hipaa/catalog.json` | catalog | yes | `DATATYPE_MISMATCH` x4 |
| `trestle.workspace/system-security-plans/sample/system-security-plan.json` | system-security-plan | no | `CONSTRAINT_CARDINALITY` x1 |

The other 39 documents produced no ERROR finding. Among those, sixteen also had
a complete effective data model, which is the only case where "no ERROR" means
"every reference this tool checks resolved": both `basic-catalog` examples,
both `basic-profile` examples and their resolved forms, the SP 800-53 rev 4
catalog, the SP 800-171 rev 3 and SP 800-218 catalogs, all four SP 800-53 rev 5
baseline profiles, and four third-party documents.

## The other thing the run found: two release conventions

52 of 52 documents declare an `oscal-version` other than the vendored 1.2.3, so
every report carries a WARNING saying so. Reading them together shows something
the schema does not constrain, because `oscal-version` is declared as a plain
string with no pattern: NIST's own catalogs use both `1.2.2` and `v1.2.2`, with
the `v` prefix on CSF 2.0, SP 800-171 rev 3, SP 800-172 rev 3 and SP 800-218,
and without it on SP 800-53. A consumer keying off that field has to handle
both forms.

This is reported as a WARNING and not an error, because no published rule says
which form is correct.

## Reproducing this

```sh
uv sync --frozen
uv run python tools/survey.py tools/survey-urls.txt out.json --cache .survey-cache
```

It fetches each document once, honoring `robots.txt`, at two seconds per host,
and caches the bytes so a second run needs no network (`--offline`). The
numbers will drift as the repositories change; the JSON alongside this file is
the run of 2026-08-14. To inspect one document:

```sh
oscal-validate <file.json> --resolve <imported-catalog.json>
```

## Limits of this survey, stated plainly

- Purposive sample of 52, not random. No population estimate follows from it,
  and the five groups are not comparable to each other.
- Publishers are heavily weighted toward NIST (30 of 52), because NIST publishes
  the most OSCAL. Two of the four third-party sources publish sample data
  derived from NIST's examples, so their findings are not independent of NIST's.
- One moment in time. Every one of these repositories can change, and one of
  them was deleted between the last published guidance and this run.
- 30 of 52 documents had an incomplete effective data model, so most reference
  findings in the run are UNVERIFIABLE rather than resolved either way. The
  ERROR counts are a floor, not a total.
- Findings are relative to OSCAL 1.2.3. Every document in the sample declares
  an earlier release, and a rule that changed between releases can appear here
  as a finding about the document.
- This tool evaluates 78 of NIST's 340 published constraints, does not check
  the `TokenDatatype` pattern at all, and does not resolve profiles. A document
  with no findings has not been shown to conform; it has been shown not to
  violate the subset that was checked.
- Nothing here is a statement about any system, any vendor's security, or any
  authorization decision.
