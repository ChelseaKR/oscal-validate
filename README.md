# oscal-validate

Deterministic structural validation for
[OSCAL (Open Security Controls Assessment Language)](https://pages.nist.gov/OSCAL/)
documents, meant to run before you hand a package to anyone. Point it at a
catalog, profile, SSP, component definition, assessment plan, assessment
results, or POA&M, and it checks the things a publisher can get wrong silently:
required structure, identifier format and uniqueness, and whether the
references in the document resolve to anything.

The validation command makes no network call and no model call, ever. Same
input, same output, byte for byte. Every finding cites the published rule it
came from, with the source and the date that source was retrieved. Four
opt-in commands added under [ADR-0005](docs/adr/0005-ai-at-the-edges.md)
do call a model; they are separate subcommands, they change nothing about
the one above, and they are described in
[AI-assisted explanation and repair](#ai-assisted-explanation-and-repair-opt-in).

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

**Status:** Beta. Tagged `v0.1.0` and `v0.2.0`; nothing is published to PyPI,
so installation is from source. This is a demonstration and reference
implementation. It is not affiliated with, endorsed by, or reviewed by NIST,
FedRAMP, or StateRAMP.

```console
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

```sh
pip install .

# Two documents ship with this repository, so the first run needs nothing else
# downloaded, and shows both sides of the gate:
oscal-validate tests/fixtures/clean_catalog.json    # 0 ERROR, exit 0
oscal-validate tests/fixtures/broken_catalog.json   # 3 ERROR, exit 1

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
| 0 | Which imports were supplied, which were not, and which were supplied more than once | `IMPORT_RESOLVED`, `IMPORT_NOT_SUPPLIED`, `IMPORT_AMBIGUOUS` | The report's own audit trail for every severity below |
| 1 | Document shape against the published JSON Schema: required properties, properties the schema forbids, JSON type, arrays shorter than `minItems`, and objects no declared alternative accepts | `REQUIRED_PROPERTY_MISSING`, `PROPERTY_UNDECLARED`, `TYPE_MISMATCH`, `ARRAY_TOO_SHORT`, `NO_SCHEMA_ALTERNATIVE`, `SUBTREE_NOT_READ` | [`oscal_complete_schema.json`](https://github.com/usnistgov/OSCAL/releases/tag/v1.2.3) |
| 2 | Scalar values against the datatype the schema declares at that position: UUID form (v4 or v5), timestamps with a required timezone, URIs, non-empty markup lines, and the lower bounds on OSCAL's two integer datatypes | `DATATYPE_MISMATCH`, `DATATYPE_BELOW_MINIMUM`, `PATTERN_NOT_CHECKED` | the same schema's own datatype patterns and bounds |
| 3 | NIST's constraint layer: `is-unique`, `index` uniqueness, `index-has-key` cross-references, `has-cardinality`, and the `matches` constraints whose regex or datatype the vendored files carry | `CONSTRAINT_NOT_UNIQUE`, `CONSTRAINT_CARDINALITY`, `CONSTRAINT_VALUE_MISMATCH`, `REFERENCE_UNRESOLVED`, `REFERENCE_UNVERIFIABLE`, `CONSTRAINT_NOT_EVALUATED` | the vendored `*_metaschema_RESOLVED.xml` modules, at NIST's declared severity |
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

```console
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

`--resolve` is repeatable and takes directories, so the same file reaches it
twice for reasons that are not mistakes: a directory named twice, a directory
and a file inside it, a path with and without a trailing slash. One file
reached twice is one file, identified by its resolved path, and every one of
those spellings produces the same report as passing the file once.

What is left after that is real: **two different files answering to one name**,
which happens as soon as two publishers' `catalog.json` are handed over
together. That is `IMPORT_AMBIGUOUS`, and it is deliberately not
`IMPORT_NOT_SUPPLIED`. The documents *were* supplied; what cannot be determined
is which one the import means, so neither is admitted to the effective data
model and references into it stay UNVERIFIABLE. The finding names every
candidate path, and the fix is the opposite of the fix for a missing document —
narrow `--resolve` rather than widen it — so the report says that instead.

## GitHub Action

If the documents you deliver live in a repository, [`action.yml`](action.yml)
validates them on every pull request and annotates each finding on the file it
came from:

```yaml
name: Validate OSCAL
on: [pull_request]

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      # Prefer a commit SHA. A tag is shown for readability; v0.2.0 is the
      # first release that carries the action.
      - uses: ChelseaKR/oscal-validate@v0.2.0
        with:
          path: oscal/
```

`path` takes one document, a directory (searched recursively for `*.json`), or
a glob such as `oscal/**/*.json`. Two further inputs, both optional:

- `resolve`: space-separated documents or directories to resolve imports and
  references against, passed through as repeated `--resolve`. Same rules as
  the CLI, including the file-name matching described above, and nothing is
  fetched.
- `fail-on`: `error` (default), `warning`, or `info`. The CLI itself gates on
  ERROR and only ERROR; a lower threshold is applied by the action, from the
  counts in the CLI's own `--format json` summary. UNVERIFIABLE is gated at no
  setting, because it marks what the supplied documents cannot settle and is
  never a pass.

```yaml
      - uses: ChelseaKR/oscal-validate@v0.2.0
        id: oscal
        with:
          path: oscal/**/*.json
          resolve: baselines/ NIST_SP-800-53_rev5_catalog.json
          fail-on: warning
      - run: echo "${{ steps.oscal.outputs.unverifiable-count }} finding(s) unsettled"
```

The counts are published as outputs: `error-count`, `warning-count`,
`info-count`, `unverifiable-count`, and `files-validated`. Watch the
unverifiable count: a run of a large package with imports withheld can be
green and still have settled very little, and the number is how you see that.
The exit codes are the CLI's, unchanged: 0 when nothing meets the threshold, 1
when something does, 2 when a document could not be read. A `path` that
matches no file at all is also exit 2, because a run that validated nothing is
not a run that passed.

There is no install step and no lock file to hash-pin, because there is
nothing to install: `oscal-validate` has zero runtime dependencies and ships
`python -m oscal_validate`, so the action runs the checked-out source directly,
vendored NIST schema and metaschema included, and resolves nothing from PyPI
while it runs. `actions/setup-python` is pinned to a commit SHA and to the same
Python 3.12 the rest of this repository uses.

The gate is tested in both directions, because a gate that cannot fail is
worse than no gate: `tests/test_action_runner.py` asserts the exit code for
clean documents, gated findings, unreadable input, and a `path` that matches
nothing, and CI runs the composite action itself over the clean catalog and
over a copy with one required property removed, failing the build if the
broken copy passes.

## AI-assisted explanation and repair (opt-in)

A finding such as `CONSTRAINT_NOT_UNIQUE` at
`/catalog/groups/16/controls/23/id`, cited to a Metaschema constraint by
identifier, is correct and is not easy to act on. Four subcommands put a
language model beside the validator for the people who author these
documents. They are the direction change recorded in
[ADR-0005](docs/adr/0005-ai-at-the-edges.md), and they keep three things
fixed: the validator is the only thing that produces a finding, NIST's
published text is the only evidence, and a verifier that is not a model sits
between every reply and the screen.

```sh
pip install 'oscal-validate[ai]'          # the public anthropic SDK; nothing else changes
export ANTHROPIC_API_KEY=...              # from the environment only; never written to a file

oscal-validate explain my-ssp.json --severity ERROR
oscal-validate repair --draft my-ssp.json --label F6 --out my-ssp.patched.json
oscal-validate walkthrough my-ssp.json
oscal-validate ask "What does the is-unique constraint oscal-catalog-controls require?"
```

- **`explain`** runs the validator, labels its findings F1..Fn in report
  order, and for each selected finding gathers the NIST text that bears on
  it: the JSON reference entry at that pointer, the constraint's declaring
  element verbatim from the vendored metaschema, the Metaschema
  specification's section on that constraint kind, the concept page the rule
  cites. The model explains the finding by quoting that text. Every quote is
  looked up verbatim in the source it names, and every quotation written
  inline in the prose is looked up across all sources; one that is not there
  is withheld, its marker struck, and counted. The output says how many
  quotes verified and how many were withheld.
- **`repair --draft`** asks for an RFC 6902 patch (`add`, `remove`,
  `replace` only), applies it to a copy, and runs the deterministic validator
  on the copy with the same `--resolve` documents. What that run found is the
  report: `resolves F6; 6 finding(s) untouched; 1 other(s) also resolved; 0
  changed; 0 introduced`, with the counts before and after and a diff. The
  model claims nothing about the effect; the validator states it. Values
  only the author knows are placeholders and are listed as such. The
  original file is never written; `--out` writes the patched copy elsewhere
  and refuses the original or any `--resolve` path. A patch whose values
  carry an implementation narrative is refused whole.
- **`walkthrough`** groups the findings in the tool's fix order — supply what
  the document imports before the references it leaves unsettled, shape the
  validator could not read before what is beneath it, identifiers before
  references — labels the groups G1..Gn, and has the model narrate over the
  labels. A label the validator never produced is struck and counted; a
  group the narrative never mentions is appended with every finding in it;
  the full index is printed last. Nothing is invented and nothing is
  suppressed, and the header says how many groups the narrative covered.
- **`ask`** answers a question about OSCAL's published rules from the
  corpus, through the same verifier; with `--document`, the validator runs
  first and its findings are given to the model as labels.

**The boundary, enforced twice.** The model is instructed to refuse every
form of "is this control implemented", "is this system secure", "would this
get an ATO", "is this FedRAMP-ready", "does this satisfy AC-2", and to
redirect to structural conformance and qualified assessment. Then a
deterministic guard screens every sentence that would be shown and withholds
any that carries such a judgment, and says how many it withheld. The guard
is lexical on purpose: a guard that asked a model whether the model had
overstepped would be no guard at all. It errs toward withholding, and
sometimes withholds a sentence that was not a judgment.

**What leaves the machine.** A model call carries the findings, the corpus
passages, and excerpts of the document around each finding's location. A
system security plan can contain sensitive detail about a real system. The
default command sends nothing anywhere; the GitHub Action never runs these
commands; and a document sent through them is subject to the model
provider's handling of it.

**Honest refusals.** A document the validator cannot parse is refused
before any model call. A finding whose rule is this tool's own policy is
explained as such and never attributed to NIST. A document declaring an
OSCAL version other than 1.2.3 carries a note that every finding was judged
against 1.2.3 ([issue #8](https://github.com/ChelseaKR/oscal-validate/issues/8)).
A reply that cannot be parsed shows nothing.

**Model and provider.** The public `anthropic` SDK, default
`claude-sonnet-5`, configurable with `OSCAL_VALIDATE_AI_MODEL`;
`OSCAL_VALIDATE_AI_PROVIDER=bedrock` with `AWS_REGION` uses Amazon Bedrock
(`pip install 'oscal-validate[bedrock]'`), where the default is a different
model, `global.anthropic.claude-sonnet-4-6`. Bedrock grants model access per
account rather than per SDK, so the two defaults answer different questions:
the Bedrock one is the model every recorded eval and cassette here was actually
produced with, and Sonnet 5 returns `AccessDeniedException` on that account
whatever its entitlement API says. Set `OSCAL_VALIDATE_AI_MODEL` if your own
account is entitled to something newer. Credentials come from the
environment and are never written anywhere. `OSCAL_VALIDATE_AI_CASSETTE`
names a file of recorded replies that the commands replay without a
network, which is how the tests run and how an evaluation can be re-scored.

**Measured, with provenance.** [`docs/evals/README.md`](docs/evals/README.md)
is the write-up of the committed harness in [`evals/`](evals/). Run on
Amazon Bedrock `claude-sonnet-4-6` on 2026-08-21 (Sonnet 5 was not
available to the account that ran it): on the boundary suite of 100
adversarial phrasings, the shown text carried no judgment in 80 of 80
refuse-cases by both the guard and an independent judge call, all 80 were
explicit refusals, and all 20 structural control questions were answered;
on twelve published NIST documents with injected defects, 62 of 62 repair
drafts resolved their finding: 61 with nothing introduced anywhere, and 1
where re-validation caught and reported a finding the patch itself
introduced (never applied, never shown as clean); across 48 explanations, 61
quotes verified and 20 were withheld, every withheld one naming a source
outside the corpus; and 12 of 12 walkthroughs covered every group with no
label invented. Every results file names the provider, model, prompt
version, commit, and date, and a test rejects one that does not.

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
what you cannot see, and never bless it either. Four things always report as
UNVERIFIABLE rather than passing quietly:

- references into a document that was not supplied,
- the 227 published constraints this tool does not evaluate,
- references checked against an index that no evaluated constraint builds,
- values governed by a pattern this tool cannot compile.

The third of those is the mirror of the rule and was added after it bit. One of
the 113 constraints this tool evaluates is an `index-has-key` constraint whose
index is populated by an `index` constraint it skips, so the lookup misses every
key no matter what the document says. Reporting that as a failure would render a
rule that was never evaluated as somebody else's defect, which is the same
mistake in the other direction. That one is listed in
[`docs/CONSTRAINT-COVERAGE.md`](docs/CONSTRAINT-COVERAGE.md) under a generated
heading so the count cannot drift, and where the prose rule in check 4 reaches
the same reference and would settle it, the unsettled report is the one
published ([ADR-0006](docs/adr/0006-one-reference-one-report.md)).

### Break the gate before trusting it

`tests/test_break_the_gate.py` starts from a document proven clean, corrupts
one thing at a time (removes a required property, adds one the schema forbids,
breaks a UUID's version nibble, drops a timezone, duplicates a control id,
dangles a back-matter fragment, points a profile at a control that does not
exist, replaces a whole assembly with a scalar, empties an array the schema
requires items in, puts a port number below the schema's minimum), and asserts
each corruption is caught. A gate that has not been deliberately broken is a
gate you are trusting on faith.

Two of those tests assert the opposite direction too: a profile reference that
misses is an ERROR *only* when the catalog was supplied, and UNVERIFIABLE
otherwise; and a port range inside its bounds must stay clean, so the bound
check cannot pass by reporting everything.

The last three corruptions were added because they were not caught. A catalog
whose `metadata` was the JSON value `null` exited 0 with no ERROR finding: the
walk filed the scalar where an assembly belonged, everything below it became
unreachable, and the report was the verdict a valid document gets.
`{"catalog": null}` did the same for a document with no body at all. Separately,
a port range of `start: -1, end: 99.5` produced output byte for byte identical
to `start: 443, end: 443`, because the two facets `NonNegativeIntegerDatatype`
states, an `integer` base type and `"minimum": 0`, were both dropped on the way
out of the schema.

### Determinism

`tests/test_determinism.py` asserts byte-identical output for repeated runs,
including across separate interpreter processes, and that no timestamp or
duration appears anywhere in the report. There is nothing to seed: no sampling,
no clock, no network.

### No network in the validator, proved rather than promised

`tests/test_offline_guarantee.py` removes `socket` and runs the validator
anyway. A separate test asserts that no module inside the installed package
outside `oscal_validate/ai/` imports `urllib.request`, `http.client`,
`socket`, `requests`, `httpx`, or `anthropic`; that nothing outside `ai/`
imports `ai/`; and that `ai/` names the SDK only inside a function, so
importing it costs nothing. `tests/test_default_path_byte_identity.py` runs
the default command in a fresh process and asserts it loaded neither the
package nor the SDK, and compares its exact bytes over the fixtures and
nine published NIST documents against [`tests/golden/`](tests/golden/),
first captured from commit `6978895`, the last commit before any model-backed
command existed.

**The model-backed layer has never moved those bytes, and that is what this
gate is for.** They have moved twice, both for unrelated reasons. On
2026-08-29: the `CONSTRAINT_NOT_EVALUATED` finding for `allowed-values`
carried a sentence that said something false about NIST's `allow-other`
semantics, and correcting a sentence the report prints is a change to the
report. On 2026-09-01, cutting 0.3.0: the JSON report stamps the tool's own
version, so twelve lines moved, one per JSON golden, and the twelve text
goldens did not move at all. Both times the goldens were recaptured from the
same documents, each verified by SHA-256 against the manifest that recorded
them, and every other byte of the output is unchanged. Those two are the only
recaptures since `6978895`; [CHANGELOG.md](CHANGELOG.md) and
`tests/test_default_path_byte_identity.py` record both, and
`tests/golden/capture.py` now refuses to write a manifest smaller than the
committed one, so a recapture on a machine without the cached documents cannot
quietly shrink what this compares.

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
dangling fragments of one shape in SP 800-171 rev 3, 501 in a resolved LOW
baseline, and a catalog whose own UUID is also one of its back-matter
resources'. Every one was
verified by hand against the document before publication.

That run's own stated limit was that most of what it saw it could not settle:
5,501 references reported UNVERIFIABLE against 568 reported wrong.
[`docs/findings/2026-08-15-imports-supplied-survey.md`](docs/findings/2026-08-15-imports-supplied-survey.md)
is the same 52 documents with their imports located and handed over. **5,216 of
those 5,501 references resolved to something that exists, 178 resolved to
nothing, and 107 still cannot be settled.** All four FedRAMP rev 5 baselines
went from a combined 2,787 unanswerable control references to zero errors. The
178 are four shapes, and the largest is a parameter identifier that is one
zero-pad away from resolving: an SSP setting `ac-2_odp.01` against a baseline
that defines `ac-02_odp.01`.

The 107 that stayed unknown are a finding in their own right. Nine documents
import a profile whose only `rlink` is a GitHub release ZIP; five import a
relative path into a directory the publishing repository does not have; one
imports a back-matter UUID it never declares. And 29 were this tool's fault, a
defect the run exposed and the write-up describes.

Those two runs shared one sample, and it had two limits they both stated: seven
of the eight models, and 30 of 52 documents from NIST.
[`docs/findings/2026-08-19-widening-the-corpus-survey.md`](docs/findings/2026-08-19-widening-the-corpus-survey.md)
is 43 more documents from twenty-one publishers none of the first two reached —
the German BSI, the Australian Cyber Security Centre, NIST's BLOSSOM programme,
GSA, the OSCAL Plugfest, the Linux Foundation's OSCAL Compass, Red Hat, MITRE and
others — taking the corpus to **95 documents and all eight models**. Nine carried
at least one ERROR, each verified by hand: four UUIDs used twice in one SSP, 35
implemented requirements with no `description`, 13 control titles with newlines
in a field declared as one line, three catalog groups that hold both subgroups
and controls where NIST's schema permits either but not both, and Go's zero-value
timestamp published as a date.

The eighth model arrived with a result attached. All seven mapping collections
reported `SUBTREE_NOT_READ` at `/mapping-collection/mappings` — the whole
substance of the model is outside what this tool resolves, and it says so on
every document rather than reporting a clean run. Three of the seven also declare
an `oscal-version` from before OSCAL 1.2, a release whose schema has no mapping
model at all; that was measured against NIST's own published v1.1.2 schema, not
assumed.

That limit is gone. `mappings` is the one place in the vendored schema NIST
writes a repeatable assembly as "one, or an array of one or more" rather than
as an array, and the walk now reads both spellings
([ADR-0007](docs/adr/0007-read-the-eighth-model.md)). The seven documents above
report no `SUBTREE_NOT_READ` today and carry 31 ERROR findings between them
where the run recorded none: an `id_ref` written where the schema declares
`id-ref` and forbids anything else, a percentage written as a string where the
schema declares a decimal, an array present and empty where the schema requires
an item, and resource fragments naming a resource's `props/id` rather than its
`uuid`. The survey above is what that run found and is left as the record of
it.

The survey harness and its target lists are in [`tools/`](tools/), and all three
runs are reproducible: the findings a run records are now independent of where
its cache lives, which they were not before, and `--provenance` carries a
document's retrieval record forward into any later run that reads it from cache.

## Limits

Everything below is a thing this tool does **not** do. If a check could not be
implemented correctly it was left out and named here rather than shipped
approximate.

**It does not judge implementation.** Whether a control is implemented, whether
an assessment was performed, whether evidence supports a claim: none of that is
visible in a document's structure, and nothing in this tool looks at it. The
model-backed commands refuse the question and a guard withholds any answer
that slips through; the boundary suite in [`evals/`](evals/) measures both.

**It evaluates 113 of NIST's 340 published constraints.** Every one of the
other 227 is listed with its reason in
[`docs/CONSTRAINT-COVERAGE.md`](docs/CONSTRAINT-COVERAGE.md), which is generated
from the vendored files and checked by a test so it cannot drift, one reason
per constraint rather than one per kind. In summary: of the 200
`allowed-values` sets, 60 declare `allow-other` and 140 do not, and the
Metaschema specification makes the absent attribute mean the set is closed
("no: (default) Identifies the expected value set as closed"), so what is
missing is not a judgment about openness but the applicable-set resolution that
decides which values a value node permits; 11 of the 25 `matches` constraints
are evaluated and the other 14 name a target this tool cannot read, a datatype
the vendored schema does not define or defines without a pattern, or a regex
whose meaning depends on which of two published dialects applies; 12 `expect`
constraints each carry a Metapath `test` this tool does not implement, and the
coverage document prints each one; and exactly one target remains
outside the parsed subset — `oscal-ssp-by-component-uuid-index`, which
dereferences a second document through `doc()`. The predicate and
interior-descendant targets that used to block 25 constraints are parsed under
the bounded grammar of
[ADR-0004](docs/adr/0004-bounded-predicate-grammar.md), enumerated from the
vendored files rather than the Metapath specification. The order in which the
rest of that gap is intended to close, and what each step is waiting on, is
[`docs/EXPANSION-PLAN.md`](docs/EXPANSION-PLAN.md). A constraint is also
only applied to documents of the models its module governs, since assembly
names repeat across models and a catalog's `part` is not assessment-common's.

**It does not check the `TokenDatatype` pattern.** OSCAL's token pattern uses
the ECMA-262 Unicode property escapes `\p{L}` and `\p{N}`, which Python's `re`
module does not implement. Substituting a hand-written approximation would be a
rule encoded from memory, which is the one thing this tool refuses to do, so
those values are reported unchecked with a count.

**It parses XML with the standard library, on purpose.** The metaschema modules
are vendored, hash-pinned package data that no user supplies. Both attacks the
standard library's parser is criticized for need a DTD, so any vendored file
carrying `<!DOCTYPE` or `<!ENTITY` is refused before it reaches the parser, and
a test asserts none do. Taking a hardened third-party parser as a runtime
dependency would cost the zero-dependency property that makes the no-network
and no-model claims mechanically checkable.

**It is not a JSON Schema implementation.** The walk reads `$ref`,
`properties`, `required`, `additionalProperties`, `items`, `type`, `pattern`,
`minItems`, and `minimum`. It does not evaluate `enum` (except to suppress a
pattern finding where the schema offers a literal as an alternative), `format`,
or `contentEncoding`. `maximum`, `maxItems`, `minLength`, `maxLength`,
`uniqueItems`, `const`, `if`, and `not` are absent from the vendored schema, so
there is nothing there to evaluate. Where the schema combines alternatives in a
form the walk does not resolve, the subtree is reported `SUBTREE_NOT_READ`
rather than passed over.

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

```sh
uv sync --locked
make verify   # lockfile check + lint + format + strict types + coverage-gated tests + pip-audit
```

`make verify` is the exact gate CI runs; see [CONTRIBUTING.md](CONTRIBUTING.md)
for the individual targets. Its first step is `uv lock --check`, and the sync
uses `--locked` rather than `--frozen`: `--frozen` installs from `uv.lock`
without reading `pyproject.toml`, so it exits 0 on a lock that no longer
matches the manifest and cannot be a drift gate. The comment in the `Makefile`
records the measurement.

## Disclosure

This tool was built quickly with AI assistance (Claude), then reviewed and
tested by a human. Since ADR-0005 it also *contains* AI: the four opt-in
commands above call a model at run time, and say so in their first line of
output. The specification research was done first: the schema, the
constraint layer, and every prose rule were retrieved from NIST on 2026-08-14
and vendored before any check was written, and every ERROR reported in the
survey was verified by hand against the source document before publication.
Read the citations critically; if a cited source has changed since retrieval,
the vendored snapshot, not this tool's opinion, is what to update.

## Standards Conformance

This repository is part of a portfolio with shared engineering standards.
State against each, with an explicit reason wherever a standard does not apply,
and an explicit gap wherever one applies and is not yet met.

**How this scope was decided.** The portfolio keeps a machine-readable
applicability manifest, and this repository is not in it: as of 2026-08-15
`applicability.yml` on the standards repository's default branch has no
`oscal-validate` entry, which by that file's own header is a failure of the
weekly conformance run rather than a pass. The scope below was therefore
derived here, from each standard's own applicability section, for an offline
command-line tool with no hosted route, no HTML surface, and no persistent
store, whose opt-in model-backed commands are described above. It is this repository's reading, recorded so it can be
checked, and it is not a claim that any registry agrees with it yet.

| Standard | State | Evidence |
|---|---|---|
| Responsible-Tech Framework | Applies | [docs/RESPONSIBLE-TECH-AUDITS.md](docs/RESPONSIBLE-TECH-AUDITS.md): the harm surface is false assurance about a security authorization, and the controls target it directly. |
| Code Quality | Applies | Floors in `pyproject.toml`: Python >= 3.12, ruff >= 0.15, mypy >= 1.18 (strict), complexity <= 10, branch coverage >= 90%; locked with `uv.lock`; reproduced locally by `make verify`. |
| Security & Supply-Chain | Applies | [SECURITY.md](SECURITY.md); SHA-pinned Actions; Semgrep and full-history TruffleHog in CI; pip-audit in `make verify`; Dependabot; gitleaks in pre-commit. |
| CI/CD | Applies | `ci.yml` runs the same `make verify` gate as local development. |
| Observability | Applies (Tier C, library/CLI) | Declared in [docs/ROADMAP.md](docs/ROADMAP.md#observability). Tracing is out of scope because there is no network surface; the report on stdout is the entire observable surface, and its exit-code contract and JSON form are tested in `tests/test_cli.py`. Structured logging is opt-in under this tier and is not implemented; that is recorded as a gap, not as an exemption. |
| Performance | N/A (pure library/CLI with no hosted route and no shipped HTML, per PERFORMANCE-STANDARD section 0) | Recorded in [docs/ROADMAP.md](docs/ROADMAP.md). No latency-sensitive service and no frontend bundle exist to measure. |
| Accessibility | N/A (no graphical or web surface; plain-text terminal output plus `--format json`) | Revisit if any web or GUI surface is added. |
| Internationalization | N/A (findings and model-backed output quote English-language specification prose verbatim; see [docs/I18N.md](docs/I18N.md)) | Multilingual document *data* validates identically. |
| AI Evaluation | Applies (the four opt-in commands of ADR-0005; the validator itself has no model) | [docs/evals/README.md](docs/evals/README.md) and the committed harness in [evals/](evals/): a 100-case boundary suite scored on shown text, raw text, and explicit refusal; repair efficacy by deterministic re-validation on twelve NIST documents; citation grounding by verbatim lookup; walkthrough fidelity by label set. Results carry provider, model, prompt version, commit, and date, enforced by `tests/test_evals.py`; prompts are versioned in `oscal_validate.ai.PROMPT_VERSION`. |
| AI Development Measurement | Applies | `AI-DEV-MEASUREMENT: APPLIES` in [docs/ROADMAP.md](docs/ROADMAP.md). This repository was built with AI assistance, disclosed above, so Track A delivery and quality-debt metrics are mined portfolio-wide from git history. Track B applies to the opt-in commands and is served by the AI Evaluation row. |
| Incident Response | Applies | [docs/incidents/](docs/incidents/) holds the postmortem convention and no incident to date; [SECURITY.md](SECURITY.md) is the reporting channel. The `incident` and `sev1`-`sev4` labels exist as of 2026-09-05, each describing what that severity means for this project rather than carrying a generic word. Zero incidents so far is a count, not an exemption: the convention is exercised the first time it is needed. |
| Data Governance | Applies (L1, public non-sensitive) | Data cards in [docs/data/](docs/data/) for all three ingest sources, with hashes in [vendor/SOURCES.md](src/oscal_validate/vendor/SOURCES.md) enforced by `tests/test_vendor_integrity.py` and in [ai/corpus/MANIFEST.json](src/oscal_validate/ai/corpus/MANIFEST.json) enforced by `tests/test_ai_sources.py`. Open gap, recorded in [docs/ROADMAP.md](docs/ROADMAP.md): survey records carry the fetch outcome but no per-record fetch timestamp, so lineage is dated only at the file level. |
| Documentation | Applies | This README, [CHANGELOG.md](CHANGELOG.md), ADRs in [docs/adr/](docs/adr/), [CITATION.cff](CITATION.cff), [SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md), [docs/CONSTRAINT-COVERAGE.md](docs/CONSTRAINT-COVERAGE.md). |
| Quality & Metrics | Applies | [docs/ROADMAP.md](docs/ROADMAP.md) names every gate as AUTO, REVIEW, or a reasoned exception. |
| Release & Versioning | Applies | SemVer; `CHANGELOG.md` kept current. No release has been made yet, and no release workflow exists; that is an open gap recorded in [docs/ROADMAP.md](docs/ROADMAP.md), not a declaration that releases are out of scope. |

## License

Apache-2.0. OSCAL is a product of the National Institute of Standards and
Technology; the `usnistgov/OSCAL` repository states that the project is in the
public domain within the United States as a work of the US government, and
additionally waives copyright worldwide under CC0 1.0. The vendored files
retain their origin in [SOURCES.md](src/oscal_validate/vendor/SOURCES.md). This
project is not affiliated with, endorsed by, or reviewed by NIST, FedRAMP, or
StateRAMP.
