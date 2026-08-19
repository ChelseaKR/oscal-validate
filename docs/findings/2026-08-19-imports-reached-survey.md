# Eleven public documents settle a thousand unknowns, and 54 of them are dangling

Survey run 2026-08-19 against the same 43 published OSCAL documents as
[the constraints run](2026-08-19-constraints-reached-survey.md), with one
difference: every import those documents name was located and handed over with
`--resolve` wherever a public copy exists. Evidence:
[`2026-08-19-imports-reached-survey.json`](2026-08-19-imports-reached-survey.json),
written by [`tools/survey.py`](../../tools/survey.py) from the target list in
[`tools/survey-urls-2026-08-19-imports.txt`](../../tools/survey-urls-2026-08-19-imports.txt).

The constraints run left 1,512 references it could not settle, and the
widening run's own limits section had already named the cause: most documents'
effective data models were incomplete because nobody had handed the tool the
files their imports name. This is what happened when eleven publicly published
documents were fetched and handed over.

**What this is not.** Nothing below says anything about whether any control is
implemented, whether any system is secure, or whether any package would be
authorized. Every finding is about whether a published document conforms to
the published specification. That is a much smaller question, and it is the
only one this tool can answer.

**Nor is it a report on anyone's software.** Every finding here describes a
document as published on 2026-08-19 and its conformance to the specification
as vendored. None of it is a claim about the tools that produced those
documents. No issue or pull request was filed anywhere on the strength of this
survey, and this project is not affiliated with, endorsed by, or reviewed by
NIST, FedRAMP, or StateRAMP.

## Headline

| | count | of documents validated |
|---|---:|---:|
| Documents attempted | 43 | |
| Documents validated | 43 | 100% |
| Blocked by robots.txt | 0 | 0% |
| Carried at least one ERROR finding | 12 | 28% |
| Had a complete effective data model (every import supplied) | 30 | 70% |
| Of those 30, carried at least one ERROR | 10 | 33% |

Fifteen supporting documents were supplied to make that happen — the four the
widening run already supplied, and eleven more resolved for this run. Five of
the fifteen were already in the sample; ten had to be fetched and are **not**
surveyed themselves, because they are somebody else's effective data model
rather than documents this survey reports on. The denominator is still 43.

### What happened to the 1,512

| | count |
|---|---:|
| resolved to something that exists | 947 |
| resolved to nothing, and are now ERROR | 54 |
| still cannot be settled | 511 |

Those three numbers are the whole result. The largest is the good news, the
smallest is 54 references in published OSCAL that point at nothing — every one
verified by hand against the source documents before being published here —
and the 511 are bounded below by imports no one can fetch.

### Every finding code, both runs

| Code | imports as widened | imports supplied | change |
|---|---:|---:|---:|
| `CONSTRAINT_CARDINALITY` | 6 | 6 | 0 |
| `CONSTRAINT_NOT_EVALUATED` | 172 | 172 | 0 |
| `DATATYPE_MISMATCH` | 47 | 47 | 0 |
| `IMPORT_NOT_SUPPLIED` | 30 | 19 | -11 |
| `IMPORT_RESOLVED` | 11 | 27 | +16 |
| `NO_SCHEMA_ALTERNATIVE` | 4 | 4 | 0 |
| `OSCAL_VERSION_DIFFERS` | 43 | 43 | 0 |
| `PATTERN_NOT_CHECKED` | 38 | 38 | 0 |
| `PROPERTY_UNDECLARED` | 2 | 2 | 0 |
| `REFERENCE_UNRESOLVED` | 5 | 59 | +54 |
| `REFERENCE_UNVERIFIABLE` | 1,512 | 511 | -1,001 |
| `REQUIRED_PROPERTY_MISSING` | 36 | 36 | 0 |
| `SUBTREE_NOT_READ` | 7 | 7 | 0 |
| `TYPE_MISMATCH` | 2 | 2 | 0 |
| `UUID_NOT_UNIQUE` | 4 | 4 | 0 |

Every code that has nothing to do with cross-document references is unchanged,
to the finding. That is the control on this experiment: supplying imported
documents changed exactly what it should have changed and nothing else.

Finding totals in this run, by the severity each finding was actually recorded
at:

| Code | Severity | Count |
|---|---|---:|
| `REFERENCE_UNRESOLVED` | ERROR | 59 |
| `DATATYPE_MISMATCH` | ERROR | 47 |
| `REQUIRED_PROPERTY_MISSING` | ERROR | 36 |
| `NO_SCHEMA_ALTERNATIVE` | ERROR | 4 |
| `UUID_NOT_UNIQUE` | ERROR | 4 |
| `PROPERTY_UNDECLARED` | ERROR | 2 |
| `TYPE_MISMATCH` | ERROR | 2 |
| `OSCAL_VERSION_DIFFERS` | WARNING | 43 |
| `CONSTRAINT_CARDINALITY` | WARNING | 6 |
| `REFERENCE_UNVERIFIABLE` | UNVERIFIABLE | 511 |
| `CONSTRAINT_NOT_EVALUATED` | UNVERIFIABLE | 172 |
| `PATTERN_NOT_CHECKED` | UNVERIFIABLE | 38 |
| `SUBTREE_NOT_READ` | UNVERIFIABLE | 7 |
| `IMPORT_RESOLVED` | INFO | 27 |
| `IMPORT_NOT_SUPPLIED` | INFO | 19 |

154 ERROR, 49 WARNING, 728 UNVERIFIABLE and 46 INFO, which is every finding
the run recorded.

The eight documents already carrying ERRORs in the constraints run still do:
`ISO27001-AnnexA-to-GS%2B%2B-mapping_collection.json` and the harmonized
`mapping-collection.json`, the compliance-to-policy `assessment-results.json`,
`aws_leveraged_authorization_ssp.json`, the HIPAA and danzell-v16
`catalog.json` pair, `splunk-demo.json`, and `valid_oscal_poam_1.json`;
`dfetch.component-definition.json` was among them and gained the statement
references below.

## The 54, verified by hand

Three documents joined the ERROR column because their own imports, once
supplied, showed their references dangling, and one already-erroring document
gained the same class. Each claim below was checked against the source bytes
before publication:

- **`AWS%20Security%20Hub-component_definition.json` (BSI): 17 dangling
  control references.** The component's own import names BSI's
  Stand-der-Technik Kernel-G0 catalog; supplied, 17 of the control ids the
  component implements — underscore-prefixed UUIDs such as
  `_02e94d9c-cd23-4cb4-a6ef-7ccd7efb0869` — appear nowhere in that catalog.
  Both sampled ids were confirmed absent from the catalog bytes by hand.
- **`dfetch.component-definition.json`: 35 dangling statement references.**
  The component references statement ids ending `-stmt`
  (`so-access-control-stmt` and 34 more) against its own CRA catalog, which
  declares `so-access-control` and never the `-stmt` form. A one-suffix
  convention mismatch dangles every statement reference in the document; 35
  more of its references resolved cleanly against the same catalog.
- **`aws.json` (CivicActions): one dangling control, `sa-39`.** The
  component's import names NIST SP 800-53 **rev4**; the rev4 catalog was
  supplied from NIST's own `oscal-content` v1.0.0 tag, and it declares no
  `sa-39` — confirmed absent by hand, while `sa-22` is present. The remaining
  83 references resolved.
- **`component-definition.json` (Red Hat trestle-demo): one dangling control,
  `pr-1`,** against the ACME internal profile its import names. Confirmed
  absent from the profile bytes by hand.

The mirror result is worth the same prominence:
**`profile.json` (Red Hat `fedramp_rev5_high`) resolved all 783 of its
references** once the rev5 catalog vendored in its own repository was
supplied, and the oscal-compass end-to-end demo `system-security-plan.json`
resolved all 34 of its own the same way. A profile that heavy resolving to
zero dangling references is a statement about its publisher's pipeline that
only an import-complete run can make.

## The nineteen imports nobody can fetch

Nineteen `IMPORT_NOT_SUPPLIED` findings remain across thirteen documents, and
the reasons divide into classes that are themselves results:

- **Fragment-only imports (9):** `Keycloak-component_definition.json` (three
  times), `blossom_admin_member_ssp.json`,
  `aws_leveraged_authorization_ssp.json`,
  `Entra_ID_system-security-plan.json`, `Entra_ID_assessment-plan.json`,
  `anwendungen_APP.1.4_mobile_anwendungen_apps.json`, and
  `pqctoday-oscal-assessment-plan.json` import by `#uuid` or `#name` into
  their own back matter. Dereferencing the resource behind a back-matter
  rlink is outside this tool's scope, and is reported rather than guessed.
- **XML with no JSON twin (2):** `assessment-results_kansa_valid.json` imports
  `./ap.oscal.xml` and `plan_of_action_and_milestones.json` imports
  `../5-authorize/ssp.oscal.xml`; neither repository publishes a JSON
  serialization under a matching name. This tool reads JSON.
- **A private bucket (2):** `APP.1.1.component.json` imports
  `gs://us_rag_storage_1/...` twice — a Google Cloud Storage URI that is not
  public. A published document whose effective data model requires a private
  bucket cannot be completed by anyone but its publisher.
- **A literal placeholder (1):** the compliance-to-policy
  `assessment-results.json` imports the string `http://...`, verbatim.
- **A bare fragment (1):** `uc-01-fixed.oscal-poam.json` imports `#`, an
  href with no name at all.
- **A bare name (4):** `component-definition-gs-mapping.json` imports
  `Grundschutz++` four times. The repository publishes a
  `Grundschutz++-catalog.json`, but this tool matches an import by file name
  or file name without extension, and `Grundschutz++` names neither; guessing
  that a label means a file would be a substitution this survey is not
  entitled to make.

Those thirteen documents are exactly the 13 whose effective data models remain
incomplete, and their remaining 511 unsettled references are bounded by these
nineteen imports.

## Method, and what it can and cannot support

**The sample did not change.** Same 43 documents, same groups, same purposive
selection, same limits. **No percentage here is a population estimate**, and
the denominators mean different things between groups. What changed is the
third column of the target list: each line may now name the documents to hand
that target with `--resolve`.

**How the supporting documents were chosen.** Every unresolved import edge in
the constraints run names an href. Each was resolved to a public URL where one
exists — most inside the publisher's own repository, located by following the
href's own relative path or `trestle://` workspace path against the
repository layout — and the closure was walked to a fixed point: the GSA
profile's own catalog import and the oscal-compass profile's catalog import
were fetched in a second pass so their importers' models complete.

**One substitution, stated because it is a substitution.** The OpenC2
`example-component-definition.json` imports NIST's rev5 MODERATE baseline
profile by its XML serialization's URL. NIST publishes the same document as
JSON, the tool matches an import on the file name without its extension, and
the JSON twin was supplied; which file the import matched is recorded per
document in the evidence JSON. It is the same document in this tool's format,
and it is still a reading.

**The two runs are comparable because the code is the same.** Both were
produced by the same engine at 102 evaluated constraints; the only variable is
the resolve column. The engine's own delta against the widening run is the
subject of [the constraints run](2026-08-19-constraints-reached-survey.md),
measured separately so neither effect hides in the other.

**Everything was fetched once, politely.** Same posture as every run:
`robots.txt` first, an identifying User-Agent naming the tool and linking to
its repository, a two-second minimum interval per host, one request per
document. Supporting documents are fetched on exactly the same terms and their
own provenance is recorded separately in the evidence, under `supporting`.

**Only metadata and findings were recorded.** No value read from any document
is committed here beyond the identifiers of dangling references, which are the
finding. A document with no findings **has not been shown to conform**.
