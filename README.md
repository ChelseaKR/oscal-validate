# oscal-validate

Deterministic structural validation for [OSCAL](https://pages.nist.gov/OSCAL/)
documents, meant to run before you hand a package to anyone. Point it at a
catalog, profile, SSP, component definition, assessment plan, assessment
results, or POA&M, and it checks the things a publisher can get wrong silently:
required structure, identifier format and uniqueness, and whether the
references in the document resolve to anything.

No network calls, in any command. No model calls, ever. Same input, same
output, byte for byte. Every finding cites the published rule it came from,
with the source and the date that source was retrieved.

## Structural conformance is not evidence that a control is implemented

**This tool cannot tell you whether a control is implemented, whether a system
is secure, or whether a package would be authorized. It does not try.** It
reads a document and checks it against NIST's published schema and constraint
layer. A clean run means the document is well formed and its references resolve.
It means nothing at all about the system the document describes.

The distinction matters most in the direction people get wrong. A control this
tool has never heard of, a constraint it did not evaluate, a reference into a
document it was not given: every one of those is reported **UNVERIFIABLE**, and
UNVERIFIABLE is never rendered as a pass. A clean report always lists what was
not checked, alongside what was.

**Status:** Beta. No release has been tagged and nothing is published to PyPI.
This is a demonstration and reference implementation. It is not affiliated
with, endorsed by, or reviewed by NIST, FedRAMP, or StateRAMP.

```
$ oscal-validate my-catalog.json
model: catalog

ERROR        REFERENCE_UNRESOLVED  at=/catalog/groups/16/controls/23/parts/2/parts/0/parts/4/links/0/href
    href = #ac-2_smt.a.5
    This names an OSCAL object by its identifier, in this document's effective
    data model, and no such identifier is declared in the documents supplied.
    Every document named by an import was supplied, so the effective data model
    is complete and this reference resolves to nothing.
    rule: NIST, "URI Usage", section Linking to another OSCAL object ...
    source: https://pages.nist.gov/OSCAL/learn/concepts/uri-use/ (retrieved 2026-08-14)
```

Exit code 0 when there are no ERROR findings, 1 when there are, 2 when the
input cannot be read at all. `--format json` produces machine-readable output
with the same content.

## Why this exists

OSCAL's JSON Schema expresses shape and datatypes. Checked against the vendored
1.2.3 schema, it contains no `uniqueItems`, no `const`, no `if`, no `not`, and
no `dependentRequired`, and the string "unique within" appears zero times. It
cannot say that two controls must not share an id. It cannot say that a link's
`#` fragment has to name something that exists.

Those rules do exist and NIST does publish them, in two places the schema does
not reach:

1. **The Metaschema constraint layer**, shipped beside the schema in the
   `*_metaschema_RESOLVED.xml` release artifacts. OSCAL 1.2.3 declares 340
   constraints there: 48 `is-unique`, 20 `index`, 24 `index-has-key`, 11
   `has-cardinality`, 25 `matches`, 12 `expect`, and 200 `allowed-values`. None
   of them survive into the JSON Schema.
2. **Prose rules** in NIST's own documentation: that a UUID identifies exactly
   one object, and that a bare `#` fragment must resolve within the document's
   *effective data model*.

This tool reads all three layers. Everything it knows comes out of vendored,
hash-pinned copies of NIST's own files; there is no hand-written model of OSCAL
in this repository.

## Install and run

Python 3.12+, no runtime dependencies.

```
pip install .
oscal-validate <file.json>
oscal-validate <file.json> --format json
oscal-validate my-ssp.json --resolve baseline-profile.json --resolve catalog.json
```

`--resolve` takes further OSCAL documents, or a directory of them. It is how an
imported catalog or profile gets into the picture, and it is the difference
between a definite answer and an honest "cannot tell" (see
[The effective data model](#the-effective-data-model)). Nothing is ever
fetched.

## What it checks

| # | Check | Codes | Rule source |
|---|---|---|---|
| 0 | Which imports were supplied, and which were not | `IMPORT_RESOLVED`, `IMPORT_NOT_SUPPLIED` | The report's own audit trail for every severity below |
| 1 | Document shape against the published JSON Schema: required properties, properties the schema forbids, JSON type, and objects no declared alternative accepts | `REQUIRED_PROPERTY_MISSING`, `PROPERTY_UNDECLARED`, `TYPE_MISMATCH`, `NO_SCHEMA_ALTERNATIVE`, `SUBTREE_NOT_READ` | [`oscal_complete_schema.json`](https://github.com/usnistgov/OSCAL/releases/tag/v1.2.3) |
| 2 | Scalar values against the datatype the schema declares at that position: UUID form (v4 or v5), timestamps with a required timezone, URIs, non-empty markup lines | `DATATYPE_MISMATCH`, `PATTERN_NOT_CHECKED` | the same schema's own datatype patterns |
| 3 | NIST's constraint layer: `is-unique`, `index` uniqueness, `index-has-key` cross-references, `has-cardinality` | `CONSTRAINT_NOT_UNIQUE`, `CONSTRAINT_CARDINALITY`, `REFERENCE_UNRESOLVED`, `REFERENCE_UNVERIFIABLE`, `CONSTRAINT_NOT_EVALUATED` | the vendored `*_metaschema_RESOLVED.xml` modules, at NIST's declared severity |
| 4 | One UUID, one object, across the whole document | `UUID_NOT_UNIQUE` | [Identifier Use and UUIDs](https://pages.nist.gov/OSCAL/learn/concepts/identifier-use/) |
| 5 | Identifier references the constraint layer does not cover: `control-id`, `with-id`, `param-id`, `statement-id`, and bare `#` fragments | `REFERENCE_UNRESOLVED`, `REFERENCE_UNVERIFIABLE` | [URI Usage](https://pages.nist.gov/OSCAL/learn/concepts/uri-use/) |
| 6 | Which OSCAL release the document was authored against, versus the one it was judged by | `OSCAL_VERSION_DIFFERS` | the schema's own `oscal-version` description |

Every finding carries its rule citation, source URL, and retrieval date in the
output itself, in both text and JSON.

## The effective data model

This is the idea the whole tool turns on, and it is NIST's, not mine:

> "The effective data model of a document includes all objects identified with
> the document and any directly or transitively imported documents."
> — NIST, [URI Usage](https://pages.nist.gov/OSCAL/learn/concepts/uri-use/)

A catalog imports nothing, so its effective data model is itself: a reference in
it that resolves nowhere is **wrong**, and the tool says ERROR. A profile
imports a catalog, so its effective data model is invisible unless the catalog
is handed over: the same unresolved reference is **unknown**, and the tool says
UNVERIFIABLE and names the file it was missing.

```
$ oscal-validate baseline_profile.json
UNVERIFIABLE REFERENCE_UNVERIFIABLE  at=/profile/imports/0/include-controls/0/with-ids/3
    with-ids = ac-2
    ... 1 imported document(s) named by this document were not supplied
    (NIST_SP-800-53_rev5_catalog.xml), so the effective data model is
    incomplete. Supply the imported document with --resolve to settle this.

$ oscal-validate baseline_profile.json --resolve NIST_SP-800-53_rev5_catalog.json
0 ERROR
```

Imports are matched to supplied files by file name, and by file name without
its extension when that fails, because a JSON profile in the wild routinely
imports the XML serialization of its catalog. Which file each import matched is
reported, so an UNVERIFIABLE finding always comes with the reason it could not
be settled.

## Methodology

### Severities, honestly defined

- **ERROR**: the document violates a cited structural rule. Gates the exit code.
- **WARNING**: a cited signal that something is very likely wrong, or a NIST
  constraint declared at `level="WARNING"`. Severity for constraint findings is
  NIST's, not this tool's.
- **INFO**: worth a human look, not a defect.
- **UNVERIFIABLE**: the answer cannot be determined from the documents supplied,
  and the tool refuses to guess. Never rendered as a pass or a fail, never
  gates the exit code.

The rule behind UNVERIFIABLE is the rule behind the whole tool: never punish
what you cannot see, and never bless it either. Three things always report as
UNVERIFIABLE rather than passing quietly:

- references into a document that was not supplied,
- the 262 published constraints this tool does not evaluate,
- values governed by a pattern this tool cannot compile.

### Break the gate before trusting it

`tests/test_break_the_gate.py` starts from a document proven clean, corrupts
one thing at a time (removes a required property, adds one the schema forbids,
breaks a UUID's version nibble, drops a timezone, duplicates a control id,
dangles a back-matter fragment, points a profile at a control that does not
exist), and asserts each corruption is caught. A gate that has not been
deliberately broken is a gate you are trusting on faith.

One of those tests asserts the opposite direction too: a profile reference that
misses is an ERROR *only* when the catalog was supplied, and UNVERIFIABLE
otherwise.

### Determinism

`tests/test_determinism.py` asserts byte-identical output for repeated runs,
including across separate interpreter processes, and that no timestamp or
duration appears anywhere in the report. There is nothing to seed: no sampling,
no clock, no network.

### No network, proved rather than promised

`tests/test_offline_guarantee.py` removes `socket` and runs the validator
anyway. A separate test asserts that no module inside the installed package
imports `urllib.request`, `http.client`, `socket`, `requests`, or `httpx`.

The one thing in this repository that opens a socket is
[`tools/fetch.py`](tools/fetch.py), a development harness that is not installed
and is not reachable from the CLI. It exists to collect the documents behind
[`docs/findings/`](docs/findings/). Its posture — robots.txt fetched first and
obeyed with no override flag, an unreachable robots.txt treated as a complete
disallow per RFC 9309 2.3.1.4, an identifying User-Agent, five redirects with
robots re-checked at each hop, a byte cap, a timeout, and a per-host rate limit
a site's `Crawl-delay` can lengthen — is tested against a server on localhost.

## Pointed at reality

[`docs/findings/2026-08-14-published-oscal-survey.md`](docs/findings/2026-08-14-published-oscal-survey.md)
is what came back from running this against 52 published OSCAL documents,
26.1 MB across seven of the eight models, from NIST, FedRAMP, and four
third-party publishers. Thirteen carried at least one ERROR. Among them: a link
in NIST SP 800-53 rev 5 naming a control statement that does not exist, 64
dangling fragments in SP 800-171 rev 3, 501 in a resolved LOW baseline, and a
catalog whose own UUID is also one of its back-matter resources'. Every one was
verified by hand against the document before publication.

The survey harness and its target list are in [`tools/`](tools/), and the run
is reproducible.

## Limits

Everything below is a thing this tool does **not** do. If a check could not be
implemented correctly it was left out and named here rather than shipped
approximate.

**It does not judge implementation.** Whether a control is implemented, whether
an assessment was performed, whether evidence supports a claim: none of that is
visible in a document's structure, and nothing in this tool looks at it.

**It evaluates 78 of NIST's 340 published constraints.** Every one of the other
262 is listed with its reason in
[`docs/CONSTRAINT-COVERAGE.md`](docs/CONSTRAINT-COVERAGE.md), which is generated
from the vendored files and checked by a test so it cannot drift. In summary:
200 `allowed-values` sets mostly declare `allow-other`, so a value outside them
is not necessarily a violation; 25 `matches` and 12 `expect` constraints need a
Metapath evaluator this tool does not implement; 25 have target expressions with
predicates or function calls outside the Metapath subset it parses. A
constraint is also only applied to documents of the model its module governs,
since assembly names repeat across models.

**It does not check the `TokenDatatype` pattern.** OSCAL's token pattern uses
the ECMA-262 Unicode property escapes `\p{L}` and `\p{N}`, which Python's `re`
module does not implement. Substituting a hand-written approximation would be a
rule encoded from memory, which is the one thing this tool refuses to do, so
those values are reported unchecked with a count.

**It is not a JSON Schema implementation.** The walk reads `$ref`,
`properties`, `required`, `additionalProperties`, `items`, `type`, and
`pattern`. It does not evaluate `enum` (except to suppress a pattern finding
where the schema offers a literal as an alternative), `minItems`, `minimum`,
`format`, `contentEncoding`, or `uniqueItems`. Where the schema combines
alternatives in a form it does not resolve, the subtree is reported
`SUBTREE_NOT_READ` rather than passed over.

**It does not resolve profiles.** A profile's `modify`, `merge`, and
`insert-controls` are not applied, so it cannot check anything that is only
true of the resolved catalog. Profile `by-id` and `objective-id` references,
which are only resolvable after resolution, are not checked.

**It checks no referential integrity in the assessment models.** The
`oscal_assessment-common`, `oscal_assessment-results`, and `oscal_poam` modules
declare zero `index` and zero `index-has-key` constraints, so NIST publishes no
rule tying a finding's `observation-uuid` to an observation that exists.
Implementing that check here would mean inventing a rule and citing myself for
it.

**It cannot tell you a resolved reference is the wrong one.** If a link points
at a real identifier belonging to the wrong control, it resolves, and this tool
passes it in silence. See Finding 1 in the survey for a live example.

**One stated interpretation.** The Metaschema specification says a key-field
that selects nothing contributes a null to the key. Read literally, every
object missing an entire key would collide with every other; NIST's own
catalogs contain many properties with no `uuid` and are not treated as invalid.
So an entry whose composite key is null in *every* part is left out of the
index and out of the uniqueness comparison. Entries with some parts present are
compared with the absent parts as nulls. This is the one place the tool chooses
a reading, and it says so in the code and here.

## Where the rules come from

The schema and the thirteen metaschema modules are vendored unmodified in
[`src/oscal_validate/vendor/oscal/`](src/oscal_validate/vendor/oscal/), with
source URLs, retrieval dates, and SHA-256 hashes recorded in
[SOURCES.md](src/oscal_validate/vendor/SOURCES.md) and enforced by
`tests/test_vendor_integrity.py`, which also fails if a file arrives in
`vendor/` without a hash row. All fourteen were retrieved 2026-08-14 from the
OSCAL v1.2.3 release. Prose rules are quoted verbatim in
`src/oscal_validate/rules.py` with their page URLs and the date each page said
it was last updated. No rule is encoded from memory.

## Development

Uses [`uv`](https://docs.astral.sh/uv/) with a locked toolchain
(Python 3.12, see `.python-version`):

```
uv sync --frozen
make verify   # lint + format + strict types + coverage-gated tests + pip-audit
```

`make verify` is the exact gate CI runs; see [CONTRIBUTING.md](CONTRIBUTING.md)
for the individual targets.

## Disclosure

This tool was built quickly with AI assistance (Claude), then reviewed and
tested by a human. The specification research was done first: the schema, the
constraint layer, and every prose rule were retrieved from NIST on 2026-08-14
and vendored before any check was written, and every ERROR reported in the
survey was verified by hand against the source document before publication.
Read the citations critically; if a cited source has changed since retrieval,
the vendored snapshot, not this tool's opinion, is what to update.

## Standards Conformance

This repository is part of a portfolio with shared engineering standards.
Status against each, with an explicit reason wherever a standard does not
apply.

| Standard | Status | Evidence |
|---|---|---|
| Responsible-Tech Framework | Applies | [docs/RESPONSIBLE-TECH-AUDITS.md](docs/RESPONSIBLE-TECH-AUDITS.md): the harm surface is false assurance about a security authorization, and the controls target it directly. |
| Code Quality | Applies | Floors in `pyproject.toml`: Python >= 3.12, ruff >= 0.15, mypy >= 1.18 (strict), complexity <= 10, branch coverage >= 90%; locked with `uv.lock`; reproduced locally by `make verify`. |
| Security & Supply-Chain | Applies | [SECURITY.md](SECURITY.md); SHA-pinned Actions; Semgrep and full-history TruffleHog in CI; pip-audit in `make verify`; Dependabot; gitleaks in pre-commit. |
| CI/CD | Applies | `ci.yml` runs the same `make verify` gate as local development. |
| Observability | N/A (single-shot CLI; no service, no telemetry, nothing reported anywhere; the report on stdout is the entire observable surface) | Exit-code contract and JSON output tested in `tests/test_cli.py`. |
| Accessibility | N/A (no graphical or web surface; plain-text terminal output plus `--format json`) | Revisit if any web or GUI surface is added. |
| Internationalization | N/A (findings quote English-language specification prose verbatim; see [docs/I18N.md](docs/I18N.md)) | Multilingual document *data* validates identically. |
| AI Evaluation | N/A (deterministic rule engine; no model, prompt, retrieval, embedding, or LLM call anywhere; AI-assisted authoring disclosed above) | Zero runtime dependencies makes the no-model claim mechanically checkable. |
| Documentation | Applies | This README, [CHANGELOG.md](CHANGELOG.md), ADRs in [docs/adr/](docs/adr/), [CITATION.cff](CITATION.cff), [SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md), [docs/CONSTRAINT-COVERAGE.md](docs/CONSTRAINT-COVERAGE.md). |
| Quality & Metrics | Applies | [docs/ROADMAP.md](docs/ROADMAP.md) names every gate as AUTO, REVIEW, or a reasoned exception. |
| Release & Versioning | Applies | SemVer; `CHANGELOG.md` kept current. No release has been made yet. |

## License

Apache-2.0. OSCAL is a product of the National Institute of Standards and
Technology; the `usnistgov/OSCAL` repository states that the project is in the
public domain within the United States as a work of the US government, and
additionally waives copyright worldwide under CC0 1.0. The vendored files
retain their origin in [SOURCES.md](src/oscal_validate/vendor/SOURCES.md). This
project is not affiliated with, endorsed by, or reviewed by NIST, FedRAMP, or
StateRAMP.
