# The eighth model, and what publishers who are not NIST write

Survey run 2026-08-19 against 43 published OSCAL documents from twenty-one
publishers that the first two runs did not reach. Evidence:
[`2026-08-19-widening-the-corpus-survey.json`](2026-08-19-widening-the-corpus-survey.json),
written by [`tools/survey.py`](../../tools/survey.py) from the target list in
[`tools/survey-urls-2026-08-19.txt`](../../tools/survey-urls-2026-08-19.txt).

The [2026-08-14](2026-08-14-published-oscal-survey.md) and
[2026-08-15](2026-08-15-imports-supplied-survey.md) runs shared one sample of 52
documents and stated two limits on themselves. This run is an attempt on both.

The first limit was coverage: seven of OSCAL's eight models appeared and one did
not. OSCAL 1.2 added `mapping-collection`, no document in the sample used it, and
so a whole model's worth of the vendored schema had never met a real file.

The second was concentration: 30 of the 52 documents were NIST's, and two of the
four third-party publishers derived their samples from NIST's examples, so their
findings were not independent of NIST's. This list is deliberately the other way
round. No target here comes from `usnistgov/oscal-content`; NIST appears only as
a supporting document that other people's profiles import.

**What this is not.** Nothing below says anything about whether any control is
implemented, whether any system is secure, or whether any package would be
authorized. Every finding is about whether a published document conforms to the
published specification. That is a much smaller question, and it is the only one
this tool can answer.

**Nor is it a report on anyone's software.** Every finding here describes a
document as published on 2026-08-19 and its conformance to the specification as
published on 2026-08-14. None of it is a claim about the tools that produced
those documents. No issue or pull request was filed anywhere on the strength of
this survey, and this project is not affiliated with, endorsed by, or reviewed by
NIST, FedRAMP, StateRAMP, BSI, or the ACSC.

## Headline

| | count | of documents validated |
|---|---:|---:|
| Documents attempted | 43 | |
| Documents validated | 43 | 100% |
| Blocked by robots.txt | 0 | 0% |
| Carried at least one ERROR finding | 9 | 21% |
| Had a complete effective data model (every import supplied) | 21 | 49% |
| Of those 21, carried at least one ERROR | 6 | 29% |

Eight supporting documents were supplied. Five were already in the sample and
three had to be fetched; none is surveyed, so the denominator is 43.

### Every model, at last

| Model | 2026-08-15 sample | this sample | corpus |
|---|---:|---:|---:|
| `catalog` | 13 | 7 | 20 |
| `profile` | 12 | 5 | 17 |
| `component-definition` | 6 | 11 | 17 |
| `system-security-plan` | 9 | 4 | 13 |
| `assessment-plan` | 4 | 3 | 7 |
| `assessment-results` | 4 | 3 | 7 |
| `plan-of-action-and-milestones` | 4 | 3 | 7 |
| `mapping-collection` | **0** | **7** | **7** |
| | 52 | 43 | 95 |

All eight OSCAL models are now represented by real published documents. That
sentence needs an immediate qualification, and it is Finding 1.

### Every finding code in this run

| Code | Severity | Count |
|---|---|---:|
| `DATATYPE_MISMATCH` | ERROR | 47 |
| `REQUIRED_PROPERTY_MISSING` | ERROR | 36 |
| `REFERENCE_UNRESOLVED` | ERROR | 5 |
| `NO_SCHEMA_ALTERNATIVE` | ERROR | 4 |
| `UUID_NOT_UNIQUE` | ERROR | 4 |
| `PROPERTY_UNDECLARED` | ERROR | 2 |
| `TYPE_MISMATCH` | ERROR | 2 |
| `OSCAL_VERSION_DIFFERS` | WARNING | 43 |
| `CONSTRAINT_CARDINALITY` | WARNING | 6 |
| `IMPORT_NOT_SUPPLIED` | INFO | 30 |
| `IMPORT_RESOLVED` | INFO | 11 |
| `REFERENCE_UNVERIFIABLE` | UNVERIFIABLE | 1,620 |
| `CONSTRAINT_NOT_EVALUATED` | UNVERIFIABLE | 258 |
| `PATTERN_NOT_CHECKED` | UNVERIFIABLE | 38 |
| `SUBTREE_NOT_READ` | UNVERIFIABLE | 7 |

Four of those codes had never fired before. `NO_SCHEMA_ALTERNATIVE`,
`PROPERTY_UNDECLARED`, `REQUIRED_PROPERTY_MISSING` and `SUBTREE_NOT_READ` are all
implemented on `main` and all were unexercised by any of the 52 documents in the
first sample. Widening the corpus reached four checks that a year of NIST and
FedRAMP content had not.

## Method, and what it can and cannot support

Same posture as the first two runs. `robots.txt` fetched first and obeyed with no
override flag, an identifying User-Agent, two seconds per host, and the bytes
cached so a re-run needs no network. Nothing was fetched that `robots.txt`
disallowed and nothing was worked around; no host disallowed this tool.

**Every ERROR below was verified by hand against the source document before it
was published here.** Where that verification needed a schema other than the
vendored one -- because a document declares an older OSCAL version -- the schema
for the declared version was fetched from NIST's own releases and read. Two
findings changed status during that check and both are recorded as they came out.

**Selection.** Publishers were found by searching public code hosting for
documents whose root element is one of the eight OSCAL models. That is a
convenience sample of what is indexable and public, not a census. Where a
publisher sorts its own content by validity -- the OSCAL Plugfest repository has
`Valid`, `Not Valid`, `Partial` and `Untested` directories -- only documents the
publisher files under `Valid` were taken as targets, so that a finding against
one is a finding about something somebody meant to be conformant. The single
exception is deliberate and named: one `Untested` catalog was included because it
is the only public OSCAL rendering of the FedRAMP 20x key security indicators.

**Licensing.** Recorded per publisher in
[`../data/published-oscal-corpus.md`](../data/published-oscal-corpus.md).
Several of these repositories publish no licence at all. As with the first two
runs, only metadata and finding codes are recorded here and no value read from
any document is committed to this repository, so nothing here redistributes
anyone's content.

## Finding 1: the eighth model is in the corpus, and its content is unread

Seven mapping collections were validated. Every one of them produced this:

```
UNVERIFIABLE SUBTREE_NOT_READ  at=/mapping-collection/mappings
```

`/mapping-collection/mappings` is the entire substance of a mapping collection.
Everything this tool checked in those seven documents was metadata, provenance
and back matter; the mappings themselves -- the source controls, the target
controls, and the relationship asserted between them -- were not read by any rule
in this tool, because the schema combines alternatives there in a form the
walker does not resolve.

So the honest statement of coverage is narrower than "all eight models are
covered". It is: **the eighth model is now represented in the corpus, and the
first thing the corpus proved is that the tool cannot read the eighth model's
content.** That is worth more than a clean run would have been. A clean run would
have been indistinguishable from this one at the level of ERROR counts, and the
difference is exactly the distinction the whole project turns on: 7 subtrees
reported UNVERIFIABLE rather than passed over is the tool declining, out loud, to
claim something it did not check.

`tests/test_break_the_gate.py` cannot currently seed a corruption inside
`/mapping-collection/mappings` and see it caught, because nothing there is
checked. Filed as an issue rather than fixed here.

## Finding 2: three of seven mapping collections declare an OSCAL version that has no mapping model

| Publisher | declared `oscal-version` | mapping model exists in that release? |
|---|---|---|
| BSI (`ISO27001-AnnexA-to-GS++-mapping_collection.json`) | 1.2.2 | yes |
| OSCAL Compass (`nist_ai_rmf_to_iso_42001`) | 1.2.1 | yes |
| OSCAL Compass (`PCI_v4-to-NIST_800-53_rev4`) | 1.2.1 | yes |
| Sam Aydlette (`SP800-171r2-to-SP800-53r4.mapping.json`) | 1.2.2 | yes |
| OSCAL Compass (`NIST-800-53_rev4-to-Harmonized_V1.0`) | **1.1.2** | **no** |
| Nick Mahling (`iso27001-nistcsf`) | **1.1.3** | **no** |
| OSCAL Compass / compliance-trestle (`soc2`) | **1.0.4** | **no** |

The right-hand column is measured, not assumed. NIST's own
`oscal_complete_schema.json` for v1.1.2 was fetched and read: it contains zero
definitions whose name mentions `mapping`, and `mapping-collection` is not among
the eight root elements it accepts. The model arrived in OSCAL 1.2.

Three documents therefore declare conformance to a release of OSCAL in which
their own root element does not exist. This is not a case of the tool judging a
document against the wrong version -- there is no version 1.1.2 shape for a
mapping collection to conform to. `OSCAL_VERSION_DIFFERS` fires on all three, at
WARNING, which is the right severity for it and is why it is not counted among
the errors.

## Finding 3: 100 ERROR findings, hand-verified, in nine documents

Nine of 43 documents carried at least one ERROR. Every one was checked against
the source before publication here. They fall into four groups.

### 3a. Identifiers that are not what OSCAL says an identifier is

`aws_leveraged_authorization_ssp.json` (NIST BLOSSOM) reuses four UUIDs. Each
appears exactly twice, and the pairs are structurally parallel: statement 0 and
statement 1 of implemented requirement 0 carry the same UUIDs as statement 0 and
statement 1 of implemented requirement 1, as do the responsibility UUIDs beneath
them. That is the signature of a copied block, and a UUID in OSCAL identifies one
object.

`assessment-results.json` (OSCAL Compass, compliance-to-policy-go) accounts for
32 of the 47 `DATATYPE_MISMATCH` findings. Three distinct causes, all verified in
the file: UUIDs of the form `6fae08e0-93fc-11ee-a029-62f79297f1b7`, whose version
nibble is `1` where OSCAL requires a type 4 or type 5 UUID; the timestamp
`0001-01-01T00:00:00Z`, which is Go's zero value for a time and is outside the
year range the OSCAL datetime pattern accepts; and multi-line Kubernetes event
YAML placed in fields the schema declares as single-line. The same document is
also missing a required `reviewed-controls` on its first result.

### 3b. A single-line field with more than one line in it

`catalog.json` (sbomify, UK Cyber Essentials question set) carries 13
`DATATYPE_MISMATCH` findings, every one of them a control `title` containing an
embedded newline. `MarkupLineDatatype` declares the pattern `^[^\n]+$` and the
description "A single line of Markdown content". These titles are questionnaire
prompts of two and three paragraphs. The content is fine; the field it is in is
declared to hold one line.

### 3c. A group that holds both subgroups and controls

The same sbomify catalog produced three `NO_SCHEMA_ALTERNATIVE` findings, and
this one is subtle enough to be worth stating in full. NIST declares
`oscal-complete-oscal-catalog:group` as an `anyOf` over two alternatives. Both
require `title` and both set `"additionalProperties": false`. The first permits
`groups` and not `controls`; the second permits `controls` and not `groups`.

A group may therefore contain subgroups, or controls, but not both. Three of
sbomify's groups contain both, so they satisfy neither alternative and no
alternative in the published schema describes them. Nothing in the group's own
prose says this; it falls out of the shape of the schema.

### 3d. Assemblies missing a property the schema requires

`dfetch.component-definition.json` (dfetch, an EU Cyber Resilience Act component
definition) is missing `description` on all 35 of its implemented requirements.
NIST titles that assembly "Control Implementation", which is confusing --
`control-implementation` is a different assembly titled "Control Implementation
Set" -- but the requirement is unambiguous: `implemented-requirement` requires
`uuid`, `control-id` and `description`, and these have the first two. The same
document's `document-ids[0].scheme` is the string `uri`, which is not a URI.

`splunk-demo.json` (GovReady) declares `components` as an object where the schema
declares an array. See Finding 4; this is the one ERROR in the run whose status
against the document's own declared version could not be settled.

`ISO27001-AnnexA-to-GS%2B%2B-mapping_collection.json` (BSI) carries `qa-note` and
`qa-reviewed` under `provenance`, which `mapping-provenance` does not declare and
which its `"additionalProperties": false` forbids. **This one was checked against
the version the document declares.** BSI declares `oscal-version: 1.2.2`; NIST's
v1.2.2 schema was fetched and its `mapping-provenance` has exactly the same ten
properties and the same `additionalProperties: false` as 1.2.3. The document does
not conform to the release it names. OSCAL's answer for publisher-specific
annotation is `props`, which the same assembly permits.

`mapping-collection.json` (OSCAL Compass, harmonized mapping) declares
`method` as an object `{"value": ..., "ns": ...}` where the schema declares a
string constrained to `human`, `automation` or `hybrid`, and a `confidence-score`
of `{"score", "description"}` where the alternatives permit only `category` or
`percentage`. This is the document from Finding 2 that declares 1.1.2, so both
findings are true against 1.2.3 and untestable against a release that has no
mapping model at all.

`catalog.json` (OSCAL Compass, HIPAA 2.0.0) has `last-modified` of
`2025-08-14T14:07:12.346307`, with no timezone offset. OSCAL's datetime datatype
is named `DateTimeWithTimezoneDatatype` and its description is "a required
timezone".

`valid_oscal_poam_1.json` (OSCAL Plugfest 2025) has five fragment references --
one party link and four pieces of relevant evidence -- naming UUIDs that appear
nowhere in the document. Its effective data model is complete, so these are wrong
rather than unknown.

## Finding 4: one ERROR could not be verified against the version its document declares

`splunk-demo.json` declares `oscal-version: 1.0.0-rc1`, a release candidate from
before OSCAL 1.0. Its `components` is an object keyed by identifier rather than
an array, which the vendored 1.2.3 schema rejects with `TYPE_MISMATCH`.

NIST does not publish a standalone JSON schema as a release asset for that tag --
only `.zip` and `.tar.bz2` archives -- so the check that settled the BSI case
could not be run here. The finding is therefore reported as what it is: true
against the vendored schema, and **unverified** against the pre-1.0 release the
document names. It is one finding out of a hundred and it is called out rather
than averaged away, because a survey that quietly counted an unverified finding
alongside ninety-nine verified ones would be making the same mistake it exists to
catch.

## Every document that carried an ERROR

| Document | Publisher | ERRORs | Effective model complete |
|---|---|---:|---|
| `ISO27001-AnnexA-to-GS%2B%2B-mapping_collection.json` | BSI (Germany) | 2 | yes |
| `aws_leveraged_authorization_ssp.json` | NIST BLOSSOM | 4 | no |
| `valid_oscal_poam_1.json` | OSCAL Plugfest 2025 | 5 | yes |
| `mapping-collection.json` (harmonized) | OSCAL Compass | 2 | yes |
| `catalog.json` (HIPAA 2.0.0) | OSCAL Compass | 1 | yes |
| `assessment-results.json` | OSCAL Compass | 33 | no |
| `splunk-demo.json` | GovReady | 1 | yes |
| `catalog.json` (Cyber Essentials) | sbomify | 16 | yes |
| `dfetch.component-definition.json` | dfetch | 36 | no |

The 34 documents not listed carried no ERROR. That is not a statement that they
conform. A document with a complete effective data model and no ERROR
**has not been shown to conform**, only to have survived the subset of the
specification this tool evaluates. For the seven mapping collections that subset
is conspicuously small, per Finding 1.

## Reproducing this

```sh
uv sync --locked
uv run python tools/survey.py tools/survey-urls-2026-08-19.txt out.json \
  --cache .survey-cache \
  --provenance docs/findings/2026-08-14-published-oscal-survey.json
```

`--provenance` carries forward the retrieval record for documents an earlier run
already fetched, so a target that this run read from the cache still carries the
HTTP status, final URL, redirect chain and `robots.txt` outcome of the fetch that
put it there. A second run needs no network at all with `--offline`.

The numbers will drift as the repositories change; the JSON alongside this file
is the run of 2026-08-19. To inspect one document:

```sh
oscal-validate <file.json> --resolve <imported-catalog.json>
```

## Limits of this survey, stated plainly

- Purposive sample of 43, not random.
  No percentage here is a population estimate, and the seven groups are not
  comparable to each other.
- Twenty-two of the 43 had an incomplete effective data model, so most reference
  findings in this run are UNVERIFIABLE rather than settled either way. The 1,620
  `REFERENCE_UNVERIFIABLE` against 5 `REFERENCE_UNRESOLVED` is the same shape the
  2026-08-14 run had before its imports were supplied, and the same remedy
  applies: the imports these documents name are mostly XML, `trestle://` URIs,
  `gs://` bucket paths, bare strings that are not URIs at all, or files inside
  private repositories. Those are recorded and are themselves findings.
- The mapping model's content is unread, so its seven documents contribute
  almost nothing but metadata findings. Any comparison of ERROR rates across
  models has to exclude them.
- Documents were found by searching public code hosting. A publisher who ships
  OSCAL only behind a login, or only in XML or YAML, is invisible to this method.
  Two national agencies appear here; the absence of others is not evidence that
  they publish nothing.
- Nine of these repositories publish no licence at all. Only metadata is recorded
  from any of them, but a reader wanting to redistribute the documents themselves
  should check each repository rather than this table.
