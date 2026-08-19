# What 24 more of NIST's constraints changed, run against the same 43 documents

Survey run 2026-08-19 against the same 43 published OSCAL documents as
[the widening run earlier the same day](2026-08-19-widening-the-corpus-survey.md),
with the same target list and the same supplied documents, after one change to
the tool: the bounded predicate grammar of
[ADR-0004](../adr/0004-bounded-predicate-grammar.md) took constraint coverage
from 78 to 102 of NIST's 340 published constraints. Evidence:
[`2026-08-19-constraints-reached-survey.json`](2026-08-19-constraints-reached-survey.json),
written by [`tools/survey.py`](../../tools/survey.py) from the target list in
[`tools/survey-urls-2026-08-19.txt`](../../tools/survey-urls-2026-08-19.txt),
offline, from the same cached bytes the widening run fetched.

The subject of this run is the difference the engine makes when nothing else
moves. The documents are byte-identical, the imports supplied are identical,
and the only variable is 24 constraints — every one NIST's, at NIST's declared
level, already vendored and hash-pinned — that the tool previously could not
aim.

**What this is not.** Nothing below says anything about whether any control is
implemented, whether any system is secure, or whether any package would be
authorized. Every finding is about whether a published document conforms to the
published specification. That is a much smaller question, and it is the only
one this tool can answer.

**Nor is it a report on anyone's software.** Every finding here describes a
document as published on 2026-08-19 and its conformance to the specification as
vendored. None of it is a claim about the tools that produced those documents.
No issue or pull request was filed anywhere on the strength of this survey, and
this project is not affiliated with, endorsed by, or reviewed by NIST, FedRAMP,
or StateRAMP.

## Headline

| | count | of documents validated |
|---|---:|---:|
| Documents attempted | 43 | |
| Documents validated | 43 | 100% |
| Blocked by robots.txt | 0 | 0% |
| Carried at least one ERROR finding | 9 | 21% |
| Had a complete effective data model (every import supplied) | 21 | 49% |
| Of those 21, carried at least one ERROR | 6 | 29% |

Every headline number except one is identical to the widening run's, and that
is the first result: **the 24 newly reached constraints found zero new
violations in these 43 documents.** Twenty-four rules aimed for the first time,
and every document that was clean under them stayed clean. A tool with an
incentive to find problems would bury that sentence; it is the sentence the
run produced.

### What happened to the widening run's 1,620 unsettled references

| | count |
|---|---:|
| resolved to something that exists | 108 |
| resolved to nothing, and are now ERROR | 0 |
| still cannot be settled | 1,512 |

The 108 were not settled by any new document. They were settled by indexes the
engine previously could not build: NIST populates
`index-metadata-party-organizations-uuid` from `party[@type='organization']`
and the SSP's component and by-component indexes from predicate and
interior-descendant targets, all previously outside the parsed subset, so
every lookup into them was UNVERIFIABLE by construction. Built, they resolve.
All 108 sit in three documents: `blossom_admin_member_ssp.json` (41 → 34),
`aws_leveraged_authorization_ssp.json` (287 → 187), and
`valid_oscal_poam_1.json` (1 → 0).

### Every finding code, both runs

| Code | 2026-08-19, 78 constraints | 2026-08-19, 102 constraints | change |
|---|---:|---:|---:|
| `CONSTRAINT_CARDINALITY` | 6 | 6 | 0 |
| `CONSTRAINT_NOT_EVALUATED` | 258 | 172 | -86 |
| `DATATYPE_MISMATCH` | 47 | 47 | 0 |
| `IMPORT_NOT_SUPPLIED` | 30 | 30 | 0 |
| `IMPORT_RESOLVED` | 11 | 11 | 0 |
| `NO_SCHEMA_ALTERNATIVE` | 4 | 4 | 0 |
| `OSCAL_VERSION_DIFFERS` | 43 | 43 | 0 |
| `PATTERN_NOT_CHECKED` | 38 | 38 | 0 |
| `PROPERTY_UNDECLARED` | 2 | 2 | 0 |
| `REFERENCE_UNRESOLVED` | 5 | 5 | 0 |
| `REFERENCE_UNVERIFIABLE` | 1,620 | 1,512 | -108 |
| `REQUIRED_PROPERTY_MISSING` | 36 | 36 | 0 |
| `SUBTREE_NOT_READ` | 7 | 7 | 0 |
| `TYPE_MISMATCH` | 2 | 2 | 0 |
| `UUID_NOT_UNIQUE` | 4 | 4 | 0 |

Exactly two rows moved, and both are bookkeeping about the tool rather than
findings about anyone's document: `CONSTRAINT_NOT_EVALUATED` fell by 86 —
precisely two constraint groups per document, 43 × 2, because the
predicate-blocked `index`/`index-has-key`/`has-cardinality` groups stopped
being skipped — and `REFERENCE_UNVERIFIABLE` fell by the 108 above. Every
other code is unchanged, to the finding. That is the control on this
experiment: widening the engine changed exactly what an engine widening should
change, and nothing else.

Finding totals in this run, by the severity each finding was actually recorded
at:

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
| `REFERENCE_UNVERIFIABLE` | UNVERIFIABLE | 1,512 |
| `CONSTRAINT_NOT_EVALUATED` | UNVERIFIABLE | 172 |
| `PATTERN_NOT_CHECKED` | UNVERIFIABLE | 38 |
| `SUBTREE_NOT_READ` | UNVERIFIABLE | 7 |
| `IMPORT_NOT_SUPPLIED` | INFO | 30 |
| `IMPORT_RESOLVED` | INFO | 11 |

100 ERROR, 49 WARNING, 1,729 UNVERIFIABLE and 41 INFO, which is every finding
the run recorded. All six `CONSTRAINT_CARDINALITY` warnings are
`oscal-back-matter-resource-base64-rlink-cardinality`, which NIST declares at
`level="WARNING"` and which the engine evaluated before this change; the six
newly reached `has-cardinality` constraints, all on assessment parts and
activity methods, found nothing to object to in these documents.

The nine documents carrying ERRORs are the widening run's nine, unchanged:
`ISO27001-AnnexA-to-GS%2B%2B-mapping_collection.json` and the harmonized
`mapping-collection.json`, the compliance-to-policy `assessment-results.json`,
`aws_leveraged_authorization_ssp.json`, the HIPAA and danzell-v16
`catalog.json` pair, `dfetch.component-definition.json`, `splunk-demo.json`,
and `valid_oscal_poam_1.json`.

## Method, and what it can and cannot support

**The sample did not change and no network was used.** Same 43 documents, same
groups, same purposive selection, same limits, run `--offline` from the same
cache the widening run committed provenance for. **No percentage here is a
population estimate**, and the denominators mean different things between
groups.

**What was widened, exactly.** The 25 constraints the widening run reported
skipped over their target expressions break down as 24 reached and 1 declined.
The grammar that reaches them was enumerated from the vendored files rather
than from the Metapath specification — flag equality, `starts-with`,
`has-oscal-namespace`, child existence, conjunctions, unions of paths, and
interior descendants — and everything outside that enumeration still declines
with its reason ([ADR-0004](../adr/0004-bounded-predicate-grammar.md)). The
one decline is `oscal-ssp-by-component-uuid-index`, whose target dereferences
a second document through `doc()`; the lookups that read its index stay
UNVERIFIABLE and say so.

**Zero new violations is a claim about these 43 documents, not about the 24
constraints.** The gate suite seeds deliberate violations of the newly reached
constraints — a `member-of-organizations` naming no declared organization is
now a caught ERROR in `tests/test_break_the_gate.py` — so the constraints are
known to fire; these documents simply do not violate them.

**Only metadata and findings were recorded.** No value read from any document
is committed here. A document with no findings
**has not been shown to conform**: an absence of findings from 102 evaluated
constraints is a statement about 102 constraints, and NIST publishes 340.
