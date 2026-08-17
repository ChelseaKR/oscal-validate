# What changes when the validator is given the documents it was missing

Survey run 2026-08-15 against the same 52 published OSCAL documents as
[the 2026-08-14 run](2026-08-14-published-oscal-survey.md), with one difference:
every document those 52 import was located and handed over with `--resolve`
wherever a public copy exists. Evidence:
[`2026-08-15-imports-supplied-survey.json`](2026-08-15-imports-supplied-survey.json),
written by [`tools/survey.py`](../../tools/survey.py) from the target list in
[`tools/survey-urls.txt`](../../tools/survey-urls.txt).

The first run's own stated limit was that most of what it saw, it could not
settle: 5,501 references reported UNVERIFIABLE against 568 reported wrong. This
is what happened to those 5,501.

**What this is not.** Nothing below says anything about whether any control is
implemented, whether any system is secure, or whether any package would be
authorized. Every finding is about whether a published document conforms to the
published specification. That is a much smaller question, and it is the only
one this tool can answer.

**Nor is it a report on anyone's software.** Every finding here describes a
document as published on 2026-08-15 and its conformance to the specification as
published on 2026-08-14. None of it is a claim about the tools that produced
those documents. No issue or pull request was filed anywhere on the strength of
this survey, and this project is not affiliated with, endorsed by, or reviewed
by NIST, FedRAMP, or StateRAMP.

## Headline

| | count | of documents validated |
|---|---:|---:|
| Documents attempted | 52 | |
| Documents validated | 52 | 100% |
| Blocked by robots.txt | 0 | 0% |
| Carried at least one ERROR finding | 17 | 33% |
| Had a complete effective data model (every import supplied) | 37 | 71% |
| Of those 37, carried at least one ERROR | 16 | 43% |

Fifteen supporting documents were supplied to make that happen. Ten of them
were already in the sample; five had to be fetched and are **not** surveyed
themselves, because they are somebody else's effective data model rather than
documents this survey reports on. The denominator is still 52.

### What happened to the 5,501

| | count |
|---|---:|
| resolved to something that exists | 5,216 |
| resolved to nothing, and are now ERROR | 178 |
| still cannot be settled | 107 |

Those three numbers are the whole result. The largest of them is the good news,
the smallest is the interesting news, and the middle one is 178 references in
published OSCAL that point at nothing.

### Every finding code, both runs

| Code | 2026-08-14, imports withheld | 2026-08-15, imports supplied | change |
|---|---:|---:|---:|
| `CONSTRAINT_CARDINALITY` | 11 | 11 | 0 |
| `CONSTRAINT_NOT_EVALUATED` | 312 | 312 | 0 |
| `CONSTRAINT_NOT_UNIQUE` | 2 | 2 | 0 |
| `DATATYPE_MISMATCH` | 6 | 6 | 0 |
| `IMPORT_NOT_SUPPLIED` | 93 | 15 | -78 |
| `IMPORT_RESOLVED` | 7 | 100 | +93 |
| `OSCAL_VERSION_DIFFERS` | 52 | 52 | 0 |
| `PATTERN_NOT_CHECKED` | 50 | 50 | 0 |
| `REFERENCE_UNRESOLVED` | 568 | 746 | +178 |
| `REFERENCE_UNVERIFIABLE` | 5,501 | 107 | -5,394 |
| `TYPE_MISMATCH` | 8 | 8 | 0 |
| `UUID_NOT_UNIQUE` | 427 | 427 | 0 |

Every code that has nothing to do with cross-document references is unchanged,
to the finding. That is the control on this experiment: supplying an imported
catalog changed exactly what it should have changed and nothing else.

Finding totals in this run, by the severity each finding was actually recorded
at. A constraint finding carries the severity NIST declares on the constraint,
so one code can appear at two severities and `CONSTRAINT_CARDINALITY` does:

| Code | Severity | Count |
|---|---|---:|
| `REFERENCE_UNRESOLVED` | ERROR | 746 |
| `UUID_NOT_UNIQUE` | ERROR | 427 |
| `TYPE_MISMATCH` | ERROR | 8 |
| `DATATYPE_MISMATCH` | ERROR | 6 |
| `CONSTRAINT_NOT_UNIQUE` | ERROR | 2 |
| `CONSTRAINT_CARDINALITY` | ERROR | 1 |
| `OSCAL_VERSION_DIFFERS` | WARNING | 52 |
| `CONSTRAINT_CARDINALITY` | WARNING | 10 |
| `CONSTRAINT_NOT_EVALUATED` | UNVERIFIABLE | 312 |
| `REFERENCE_UNVERIFIABLE` | UNVERIFIABLE | 107 |
| `PATTERN_NOT_CHECKED` | UNVERIFIABLE | 50 |
| `IMPORT_RESOLVED` | INFO | 100 |
| `IMPORT_NOT_SUPPLIED` | INFO | 15 |

1,190 ERROR, 62 WARNING, 469 UNVERIFIABLE and 115 INFO, which is every finding
the run recorded. The ten `CONSTRAINT_CARDINALITY` warnings are all
`oscal-back-matter-resource-base64-rlink-cardinality`, which NIST declares at
`level="WARNING"`; the one error is
`oscal-implemented-requirement-by-component-cardinality`, which declares no
level and so takes the default.

## Method, and what it can and cannot support

**The sample did not change.** Same 52 documents, same five groups, same
purposive selection, same limits. **No percentage here is a population
estimate**, and the denominators mean different things between groups. What
changed is the third column of the target list: each line may now name the
documents to hand that target with `--resolve`.

**How the supporting documents were chosen.** Every `IMPORT_NOT_SUPPLIED`
finding in the first run names a file. Each name was resolved to a public URL
where one exists, and the closure was walked to a fixed point, because an
assessment plan that imports an SSP that imports a profile is not complete
until all three are in hand. Thirteen of the thirty incomplete documents needed
nothing new at all: the file they named was already in the sample and simply
had not been handed to them.

**Three substitutions, stated because they are substitutions.** This tool
matches an import to a supplied file by file name, so supplying a file is a
claim that the name means the same thing:

- `FedRAMP-SSP-OSCAL-Template.json` imports
  `FedRAMP_rev5_MODERATE-baseline-resolved-profile_catalog.json` by an absolute
  URL into `GSA/fedramp-automation`, which no longer exists. The copy of that
  file name in `OSCAL-Foundation/fedramp-automation` was supplied instead. It
  is the reachable copy, not provably the byte the URL once served.
- Three EasyDynamics samples import files by relative paths written for
  `usnistgov/oscal-content`'s directory layout. NIST's published copies were
  supplied. EasyDynamics' samples are derived from NIST's examples, so this is
  a reasonable reading and it is still a reading.
- Several imports name the XML serialization of a document published as both
  XML and JSON. The tool matches those on the file name without its extension,
  reports which file each import matched, and that is recorded per document in
  the evidence JSON.

**The two runs are comparable because the code is the same.** One defect was
found and fixed between them (see Finding 4). The imports-withheld run was
re-run on the fixed code before the comparison and produced results identical
to the committed 2026-08-14 evidence in every record, including byte counts, so
the delta above is attributable to `--resolve` and to nothing else.

**Everything was fetched once, politely.** Same posture as the first run:
`robots.txt` first, an identifying User-Agent naming the tool and linking to its
repository, a two-second minimum interval per host, one request per document.
Supporting documents are fetched on exactly the same terms and their own
provenance is recorded separately in the evidence, under `supporting`.

**Only metadata and findings were recorded.** No value read from any document
is stored in this repository. Where a finding is located inside a supporting
document, the evidence names that document by its URL rather than by a path on
the machine that ran it, so the file is reproducible anywhere.

**Every ERROR shape below was verified by hand** against the document it came
from, independently of the tool that reported it, and the two shapes that
turned out to be the tool's fault rather than the document's are Finding 4.

## Finding 1: 5,216 references were unknown and are now known-good

The clearest case is FedRAMP's rev 5 baselines. Run alone, all four are a wall
of shrugs. Given NIST SP 800-53 rev 5, every control reference in every one of
them resolves:

| Baseline | UNVERIFIABLE alone | ERROR with the catalog |
|---|---:|---:|
| `FedRAMP_rev5_HIGH-baseline_profile.json` | 1,096 | 0 |
| `FedRAMP_rev5_MODERATE-baseline_profile.json` | 882 | 0 |
| `FedRAMP_rev5_LI-SaaS-baseline_profile.json` | 480 | 0 |
| `FedRAMP_rev5_LOW-baseline_profile.json` | 329 | 0 |

2,787 control references, none of them dangling by a single identifier. The
same held for NIST's own four SP 800-53 rev 5 baselines in the first run, and
it holds for FedRAMP's now. All nine FedRAMP documents in the sample went from
zero with a complete effective data model to nine.

This is the result that only exists because somebody handed over a file, and it
is the argument for the whole design. A validator that fetches what it is
missing would have produced this number too, and would have produced whatever
number the network produced that morning.

## Finding 2: 178 references were unknown and are now known-wrong

They come in four shapes, and each shape is one convention applied
inconsistently rather than a scatter of independent mistakes.

| Shape | Count |
|---|---:|
| a `role-id` naming a role the document does not declare | 77 |
| a `set-parameter` naming a parameter the imported catalog does not define | 55 |
| a `statement-id` naming a statement the imported catalog does not define | 36 |
| a `#` fragment naming a back-matter resource that does not exist | 10 |

### 2a. Two AWS component definitions assign 62 responsibilities to a role that does not exist

`ec2.oscal.json` names `owner` as a `responsible-role` 42 times and
`s3.oscal.json` does so 20 times. Between them and the catalog they import,
`aws_security-hub.oscal.json`, exactly one role is declared, and it is `author`.
NIST's constraint layer indexes `metadata/role/@id` and requires a `role-id` to
name an entry in that index, so this is NIST's rule at NIST's declared severity,
not this tool's opinion.

Two more of the same shape, in NIST's and EasyDynamics' own examples:
`example-component.json` assigns a responsibility to `provider` and declares no
roles at all, and `example-component-definition.json` and
`component-definition-example.json` each assign two to `customer` while
declaring only `provider`.

### 2b. Parameter identifiers are one zero-pad away from resolving

This is the single most repeated shape in the run and it is worth being exact
about.

`FedRAMP-SSP-OSCAL-Template.json` sets 41 parameters, in the form
`ac-2_prm_1` through `ac-2_prm_4` and so on. The catalog it imports,
`FedRAMP_rev5_MODERATE-baseline-resolved-profile_catalog.json`, defines the
parameters of `ac-2` as `ac-02_odp.01` through `ac-02_odp.10`. Two conventions
apart: the legacy `_prm_N` naming, and the unpadded control number.

`fedramp-ssp-example_NORMALIZED_.oscal.json` gets one of the two right and
misses on the other. It sets `ac-2_odp.01` through `ac-2_odp.10`, which is the
current naming, against
`FedRAMP_rev5_HIGH-baseline-resolved-profile_catalog.json`, which defines
`ac-02_odp.01` through `ac-02_odp.10`. Ten parameters, one zero.

NIST's own `example-component-definition.json` and EasyDynamics' copy of it set
`sc-8_prm_1` and `sc-8.1_prm_1` against the SP 800-53 rev 5 catalog, which
defines those controls' parameters as `sc-08_odp` and `sc-08.01_odp`.

Nothing in the JSON Schema can catch this, because a `param-id` is a string and
`ac-2_prm_1` is a perfectly good string. Nothing catches it at authoring time
either, because the parameter being set lives in a different file.

### 2c. Statement identifiers in the FedRAMP SSP template name statements the baseline does not have

36 of them. `ac-1_smt.b.1` and `ac-1_smt.b.2` are typical: the MODERATE
resolved baseline declares `ac-1_smt.b` and no numbered children under it.
Two of the 36 are the literal string `_smt`, which is a template placeholder
that survived into the published template.

### 2d. Ten fragments name a back-matter resource that does not exist

Four are in `FedRAMP-POAM-OSCAL-Template.json`, on `relevant-evidence`, and the
UUIDs they name appear nowhere else in the document. Five are in
`fedramp-ssp-example_NORMALIZED_.oscal.json`, and four of those five are the
single character `#`, which is a fragment naming nothing at all. One is in
`FedRAMP-SSP-OSCAL-Template.json`, on a href whose UUID is a character short of
being a UUID: `#de28452-4b02-4b49-b316-59142a7633c1`.

## Finding 3: 107 still cannot be settled, and every reason is itself a finding

Fifteen documents could not be completed. Not one of them is a case of a file
being merely inconvenient to find.

**Nine documents import a profile that is a ZIP archive.** `ifa_ssp.json`,
`ssp-example.json`, `oscal_leveraged-example_ssp.json`,
`oscal_leveraging-example_ssp.json`, and NIST's assessment plan, assessment
results and POA&M examples reach them transitively, along with EasyDynamics'
`ssp-example.json` and `poam-ifa.json`. Each names a back-matter resource whose
one `rlink` is
`https://github.com/usnistgov/oscal-content/archive/refs/tags/v1.4.0.zip` or the
`v1.3.0` equivalent, with `media-type` `application/oscal.profile+zip`. The
media type is legitimate OSCAL. The consequence is that no validator working on
documents can follow the import without unpacking a release archive and then
guessing which file inside it was meant.

**Five documents import a relative path that does not exist in the repository
that publishes them.** `ifa_assessment-plan-example.json` and EasyDynamics'
`assessment-plan-ifa.json` import `../3-implementation/ssp.oscal.xml`;
`ifa_assessment-results-example.json` and `assessment-results-ifa.json` import
`./ap.oscal.xml`; `ifa_ssp-example.json` imports `../select/profile.oscal.json`.
No file of any of those three names exists anywhere in
`usnistgov/oscal-content`, and no directory named `3-implementation` or `select`
does either. These are paths from an authoring workspace that did not survive
publication.

**One document imports a UUID it does not declare.** IBM's
`system-security-plan.json` has `import-profile/href` of
`#3b66c8da-66a2-47fa-83f7-1f9e774bf726`, and its own back-matter declares no
resource with that UUID. This one is not an unfetchable file; it is a dangling
reference inside the document's own effective data model, and no `--resolve`
argument can fix it.

**And 29 of the 107 are this tool's limit, not anybody's document.** See
Finding 4.

All fifteen, with the import that could not be settled:

| Document | Group | Import that could not be settled |
|---|---|---|
| `ifa_ssp.json` | nist-example | back-matter resource whose one rlink is `v1.4.0.zip` |
| `ssp-example.json` | nist-example | back-matter resource whose one rlink is `v1.3.0.zip` |
| `oscal_leveraged-example_ssp.json` | nist-example | back-matter resource whose one rlink is `v1.4.0.zip` |
| `oscal_leveraging-example_ssp.json` | nist-example | back-matter resource whose one rlink is `v1.3.0.zip` |
| `ifa_assessment-plan.json` | nist-example | reaches `ifa_ssp.json`'s ZIP import transitively |
| `ifa_assessment-results.json` | nist-example | reaches `ifa_ssp.json`'s ZIP import transitively |
| `ifa_plan-of-action-and-milestones.json` | nist-example | reaches `ifa_ssp.json`'s ZIP import transitively |
| `ssp-example.json` (EasyDynamics) | vendor | back-matter resource whose one rlink is `v1.3.0.zip` |
| `poam-ifa.json` | vendor | reaches `ifa_ssp.json`'s ZIP import transitively |
| `ifa_assessment-plan-example.json` | nist-example | `../3-implementation/ssp.oscal.xml`, which does not exist |
| `assessment-plan-ifa.json` | vendor | `../3-implementation/ssp.oscal.xml`, which does not exist |
| `ifa_assessment-results-example.json` | nist-example | `./ap.oscal.xml`, which does not exist |
| `assessment-results-ifa.json` | vendor | `./ap.oscal.xml`, which does not exist |
| `ifa_ssp-example.json` | nist-example | `../select/profile.oscal.json`, which does not exist |
| `system-security-plan.json` (IBM) | vendor | `#3b66c8da-66a2-47fa-83f7-1f9e774bf726`, a back-matter UUID the document does not declare |

## Finding 4: the run found a defect in this tool, and it was the dangerous kind

Before the fix, this run reported 29 references as ERROR that were correct.
Every one was verified by hand: 25 `member-of-organizations` values naming a
party the document does in fact declare, and 4 `provided-uuid` values naming a
`provided` that does in fact exist.

The cause is worth writing down, because it is the exact inverse of the mistake
this tool was built to avoid. NIST populates the index behind
`member-of-organizations` with a constraint whose target is
`party[@type='organization']`. That target carries a predicate, which is outside
the Metapath subset this tool parses, so the constraint is skipped and the index
is never built. The `index-has-key` constraint that *reads* that index parses
fine and runs. A lookup into an index that was never built misses every key, so
every reference through it was reported as resolving to nothing.

This tool's whole contract is that a check it did not run is never rendered as a
pass. The mirror-image failure, a check it did not run being rendered as
somebody else's *failure*, was not covered by that contract and is worse: it
accuses a correct document on the strength of a rule that was never evaluated.

It is now covered. An `index-has-key` whose index no evaluated `index`
constraint builds reports UNVERIFIABLE, names the index, and cites the
cross-instance scoping rule rather than the constraint it could not honour.
`docs/CONSTRAINT-COVERAGE.md` gained a generated section listing exactly which
constraints are in that position, so the count cannot drift, and
`tests/test_break_the_gate.py` now asserts the non-firing direction on a
document proven clean.

Both affected constraints were in the 78 this tool counts as evaluated. They
still are: they run, and they can only ever return UNVERIFIABLE, which the
coverage table now says out loud.

The defect was invisible in the first run. Every document carrying such a
reference had an incomplete effective data model, so the finding was already
UNVERIFIABLE for the other reason. Supplying the imports is what exposed it,
which is a small argument for pointing a checker at more reality rather than
less.

## Every document that carried an ERROR

"Complete" means every document named by an import was supplied to the run.
Documents marked **new** carried no ERROR in the imports-withheld run.

| Document | Model | Complete | ERROR findings |
|---|---|---|---|
| `example-component-definition.json` | component-definition | yes | `REFERENCE_UNRESOLVED` x4; `UUID_NOT_UNIQUE` x1 |
| `example-component.json` **new** | component-definition | yes | `REFERENCE_UNRESOLVED` x1 |
| `NIST_SP-800-53_rev5_catalog.json` | catalog | yes | `REFERENCE_UNRESOLVED` x1 |
| `NIST_CSF_v2.0_catalog.json` | catalog | yes | `UUID_NOT_UNIQUE` x1 |
| `NIST_SP800-171_rev3_catalog.json` | catalog | yes | `REFERENCE_UNRESOLVED` x64 |
| `NIST_SP-800-53_rev5_LOW-baseline-resolved-profile_catalog.json` | catalog | yes | `REFERENCE_UNRESOLVED` x501 |
| `NIST_SP-800-53_rev4_MODERATE-baseline_profile.json` | profile | yes | `REFERENCE_UNRESOLVED` x2 |
| `FedRAMP-SSP-OSCAL-Template.json` | system-security-plan | yes | `CONSTRAINT_CARDINALITY` x1; `CONSTRAINT_NOT_UNIQUE` x1; `REFERENCE_UNRESOLVED` x78; `UUID_NOT_UNIQUE` x4 |
| `FedRAMP-SAP-OSCAL-Template.json` | assessment-plan | yes | `CONSTRAINT_CARDINALITY` x2; `CONSTRAINT_NOT_UNIQUE` x1; `DATATYPE_MISMATCH` x1; `UUID_NOT_UNIQUE` x3 |
| `FedRAMP-SAR-OSCAL-Template.json` | assessment-results | yes | `CONSTRAINT_CARDINALITY` x1; `DATATYPE_MISMATCH` x1; `UUID_NOT_UNIQUE` x9 |
| `FedRAMP-POAM-OSCAL-Template.json` **new** | plan-of-action-and-milestones | yes | `CONSTRAINT_CARDINALITY` x2; `REFERENCE_UNRESOLVED` x4 |
| `fedramp-ssp-example_NORMALIZED_.oscal.json` | system-security-plan | yes | `REFERENCE_UNRESOLVED` x25; `TYPE_MISMATCH` x8; `UUID_NOT_UNIQUE` x408 |
| `s3.oscal.json` **new** | component-definition | yes | `REFERENCE_UNRESOLVED` x20 |
| `ec2.oscal.json` **new** | component-definition | yes | `REFERENCE_UNRESOLVED` x42 |
| `component-definition-example.json` | component-definition | yes | `REFERENCE_UNRESOLVED` x4; `UUID_NOT_UNIQUE` x1 |
| `catalogs/hipaa/catalog.json` | catalog | yes | `DATATYPE_MISMATCH` x4 |
| `trestle.workspace/system-security-plans/sample/system-security-plan.json` | system-security-plan | no | `CONSTRAINT_CARDINALITY` x1 |

Two documents that carried ERRORs in the first run carry none here, for the
uninteresting reason that they never did: `FedRAMP-SAP-OSCAL-Template.json` and
`FedRAMP-SAR-OSCAL-Template.json` kept the same ERROR counts, and no document
lost an ERROR. The ERROR set only grew.

## Reproducing this

```sh
uv sync --locked
uv run python tools/survey.py tools/survey-urls.txt out.json --cache .survey-cache
```

The third column of each target line names the documents to hand that target
with `--resolve`. Those are fetched on the same terms as a target and are not
surveyed. To get the imports-withheld comparison, run the same command against
a copy of the target list with the third column removed. To inspect one
document:

```sh
oscal-validate <file.json> --resolve <imported-catalog.json>
```

The numbers will drift as the repositories change; the JSON alongside this file
is the run of 2026-08-15.

## Limits of this survey, stated plainly

- Purposive sample of 52, not random. No population estimate follows from it,
  and the five groups are not comparable to each other.
- Publishers are heavily weighted toward NIST, because NIST publishes the most
  OSCAL. Two of the four third-party sources publish sample data derived from
  NIST's examples, so their findings are not independent of NIST's.
- One moment in time, and a different moment from the first run by a day. The
  first run's numbers were reproduced exactly before this one was taken, so
  nothing here rests on the two runs having seen the same bytes by assumption.
- Supplying a document by file name is a claim that the name means what the
  import meant. Three cases where that claim is a judgement rather than an
  identity are named under Method.
- 15 of 52 documents still have an incomplete effective data model, so the
  ERROR count is still a floor rather than a total. It is a much tighter floor:
  115 import edges, 100 of them resolved.
- Findings are relative to OSCAL 1.2.3. Every document in the sample declares an
  earlier release, and a rule that changed between releases can appear here as
  a finding about the document.
- This tool evaluates 78 of NIST's 340 published constraints, two of which can
  only ever return UNVERIFIABLE, does not check the `TokenDatatype` pattern at
  all, and does not resolve profiles.
  A document with no findings has not been shown to conform.
  It has been shown not to violate the subset that was checked.
- Nothing here is a statement about any system, any vendor's security, or any
  authorization decision.
