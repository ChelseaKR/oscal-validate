# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **The target grammar reads a value, not only a node.** `allowed-values` and
  `matches` constrain the value of a field or a flag, so their targets end
  somewhere a node target never does: a trailing `/@name` flag step, a bare
  `@name` (which the Metaschema specification says is the flag's own value),
  or the value of the nodes a path selects. `parse_value_target` reads those
  three shapes and refuses everything else, and `select_values` reads a flag
  off a node, a scalar node itself, or the value an object writes under the
  `json-value-key` its definition declares, which is how `hash` writes its
  value under `value` and `telephone-number` under `number`. 155 of 200
  `allowed-values` targets and 18 of 25 `matches` targets now parse. Nothing
  new is evaluated by this: parsing a target is not evaluating a constraint,
  and the count stays 102 of 340.

### Fixed

- **43 constraints were attributed to the wrong node.** A constraint declared
  inside a `define-flag` constrains that flag's value wherever the flag is
  used, and the specification says its target "MUST be considered `.`,
  referring to the flag node". The collector did not descend into flag
  definitions as definitions, so those 43 recorded the enclosing assembly as
  their context and were published with the reason written for a constraint on
  an assembly. They now name the flag they are declared on, and say that
  resolving them needs a traversal through flag definitions that this tool
  does not do.
- **52 value targets were reported as blocked on the wrong thing.** They are
  blocked on their target expression, which this tool cannot read, and until
  it can, nothing about `allow-other` or a datatype matters. They say that
  now, and the 18 `matches` targets that are read say instead that what is
  missing is applying the regex or datatype they name.

### Changed

- **Every skipped constraint now says why it in particular was skipped**, not
  why its kind was. The reason is computed from what that constraint declares
  and published per constraint in
  [`docs/CONSTRAINT-COVERAGE.md`](docs/CONSTRAINT-COVERAGE.md). The 200
  `allowed-values` constraints now carry two reasons instead of one: 140 say
  their value set is closed because `allow-other` defaults to `no` where it is
  not declared, 60 say they declare `allow-other="yes"`, and both say that what
  is missing is the applicable-set resolution. Each of the 12 `expect`
  constraints prints its own `test`, so a reader can see the expression that
  went unchecked. Each of the 25 `matches` constraints names the regex or the
  datatype it would have applied.
- **The README no longer says most allowed-value sets declare `allow-other`.**
  Counted in the vendored files, 60 of 200 do. The Metaschema specification
  makes the absent attribute mean the opposite of what that sentence implied:
  "no: (default) Identifies the expected value set as closed. This is the
  implicit default value if no @allow-other is provided." The tool was not
  wrong about what it evaluates; it was wrong about why it does not.

No verdict moved and no report byte moved: 102 of 340 is still 102 of 340, and
the goldens in `tests/golden/` are untouched.

### Known wrong, and blocked

- **The one-line summary a report prints for the `allowed-values` kind still
  carries the sentence above.** It is corrected in the coverage document that
  the line points at, and it is labelled as wrong in `metaschema.py` where it
  is declared, but the line itself cannot be corrected from inside the
  repository. `ai/walkthrough.py` puts `finding.value` and the first 160
  characters of `finding.message` into the model prompt, and
  `tests/cassettes/walkthrough-nist-ssp.json` is keyed on a SHA-256 of the
  exact prompt, so one changed character misses the recording and fails
  `tests/test_ai_walkthrough.py`. Re-recording is the procedure `CONTRIBUTING.md`
  prescribes and it is a live billed call on the owner's Bedrock account. It is
  listed as an owner action in [`docs/ROADMAP.md`](docs/ROADMAP.md).

### Fixed

- **One href produced two findings, and in one case two contradicting
  verdicts (ADR-0006).** `validator.py::_deduplicate` merges the reports the
  constraint layer and the prose rule in check 4 both make about a bare `#`
  fragment. It never merged one: it keyed on `(location, value)` as each check
  spells them, and the two spell both correctly and differently, so a dangling
  back-matter reference was reported at `/catalog/metadata/links/0` and again
  at `/catalog/metadata/links/0/href`. On a `provided-by` link the two reports
  disagreed: `REFERENCE_UNVERIFIABLE` ("the index was never built, so this key
  could not be looked up in it") beside `REFERENCE_UNRESOLVED` at ERROR ("the
  effective data model is complete and this reference resolves to nothing").
  The key is now normalized, and `_prefer` decides on settledness first: where
  two reports about one reference disagree about whether the question was
  settled, the unsettled one is published, because a check that has just said
  it could not perform the lookup does not become able to perform it because
  another check came back empty. Severity ordering was rejected (it would
  silently raise NIST's own published `level`), and which check reported a
  finding is now stated in `REFERENCE_PRECEDENCE` rather than inferred from
  the citation string, which is what made normalizing the key alone convert
  the UNVERIFIABLE into an ERROR and break ADR-0002's gate test. An unsettled
  report also now cites the reason it is unsettled: an index that was never
  built is tool policy (`INDEX_NEVER_BUILT`), a document that was not supplied
  is NIST's cross-instance scope. `_prefer` had never been called with two
  findings in the whole suite; `validator.py` is now at 100% line and branch
  coverage. [Issue #22](https://github.com/ChelseaKR/oscal-validate/issues/22)

### Added

- **The eighth model is read (ADR-0007).** Every `mapping-collection` reported
  `UNVERIFIABLE SUBTREE_NOT_READ at=/mapping-collection/mappings` and nothing
  below that pointer was checked by any rule, which is the whole substance of
  the model: the source controls, the target controls, and the relationship
  between them. The blocker was one shape, enumerated from the vendored schema
  rather than guessed at. `mappings` is written
  `{"anyOf": [{"$ref": X}, {"type": "array", "items": {"$ref": X}}]}`, the only
  node a document can reach that the resolver declined, and it is written that
  way because it is the only `group-as` of 394 in the vendored metaschema
  modules with no `in-json="ARRAY"`. The walk now resolves "one X or an array
  of X" where both branches name the identical definition, and only that: two
  different targets are a real choice between alternatives and are still
  declined and reported. Required properties, forbidden properties, JSON types,
  `minItems`, UUID uniqueness and bare `#` fragment references all reach inside
  a mapping now. `tests/test_break_the_gate.py` gains a proven-clean synthetic
  mapping collection and seven corruptions inside it, every one of which
  produced 0 ERROR before this change; the seven published mapping collections
  in the corpus report no `SUBTREE_NOT_READ` and 31 ERROR findings where they
  reported none. The 2026-08-19 write-up, the data card and the README keep
  what that run found and say, with a date, that the limit is gone.
  [Issue #7](https://github.com/ChelseaKR/oscal-validate/issues/7)

### Changed

- **The documentation says what the tool is now (ADR-0005).** The README
  gains "AI-assisted explanation and repair (opt-in)": the four commands,
  what each checks before it shows anything, the boundary enforced twice,
  what leaves the machine, the honest refusals, the provider and model
  settings, and the measured numbers with their provenance. "No network,
  proved rather than promised" is rescoped to the validator and now also
  describes the goldens. The standards table moves AI Evaluation from N/A to
  Applies with the harness as evidence, AI Development Measurement's Track B
  from N/A to served, and Data Governance to three ingest sources.
  `docs/ROADMAP.md` gains rows for byte identity, the boundary, repair
  verification, citation grounding, walkthrough fidelity, corpus integrity,
  and eval provenance. `docs/RESPONSIBLE-TECH-AUDITS.md` gains section H, the
  audit of the model-backed surface, with residual risks stated.
  `docs/evals/README.md` is the eval write-up; `docs/data/nist-documentation-corpus.md`
  is the corpus's data card; `docs/I18N.md` and `CONTRIBUTING.md` cover the
  new surface; the CLI's own description no longer claims "no model calls"
  for the whole tool.

### Added

- **Every opt-in AI command discloses what it is about to send, before it
  sends it.** `explain`, `repair --draft`, `walkthrough`, and `ask` each
  print a one-line notice on stderr — naming what leaves the machine (the
  findings, NIST text passages, and document excerpts, or the question
  alone for `ask` without `--document`) and which provider it goes to —
  before the first network call, not only in `--help` and the README.
  `tests/test_ai_explain.py` exercises all four commands against a cassette
  and asserts the notice appears first. [Issue #20](https://github.com/ChelseaKR/oscal-validate/issues/20)
  records what a redaction or fixtures-only mode for these commands would
  take and why it is not trivial (owner decision: future scope, not built
  now).

- **Real-document evals: repair efficacy, citation grounding, and walkthrough
  fidelity on twelve published NIST documents (ADR-0005, item 6).**
  `evals/cases/documents.json` pins twelve `usnistgov/oscal-content`
  documents across all seven models by URL and SHA-256 (kept in the survey
  cache, never fetched by a runner, refused on a hash mismatch, recorded as
  skipped when absent). `evals/run_repair.py` injects one named defect at a
  time — the corruptions `tests/test_break_the_gate.py` already uses — takes
  the ERROR findings that appeared as targets, runs `repair --draft`, and
  counts what the deterministic validator found on re-validation.
  `evals/run_grounding.py` explains up to four findings per document,
  chosen across severities, and counts verified and withheld quotes, struck
  inline quotations, and guard-withheld sentences; and runs one walkthrough
  per document, counting groups covered, labels struck, and sentences
  withheld. Every shard runner takes `--merge`, and every results file
  carries provenance. Run on Amazon Bedrock `claude-sonnet-4-6`,
  2026-08-21: repair, 62 targets, 59 resolved with nothing introduced, 2 not
  drafted (a pointer written relative to the excerpt rather than the
  document root), 1 not resolved (a dangling fragment re-pointed at another
  non-existent UUID); grounding, 48 explanations, 61 quotes verified, 20
  withheld — every withheld quote named a source outside the corpus, and 14
  of the 48 had no verifiable quote, all of them findings whose rule is
  tool policy rather than NIST text; walkthrough, 12 of 12 documents with
  all 53 groups covered and 0 labels struck. The guard withheld 5 sentences
  across both runs; on inspection none was a judgment, which is the
  direction ADR-0005 says it should err.

- **`oscal-validate walkthrough`: where to start on a long report, with
  nothing invented and nothing suppressed (ADR-0005, items 1 and 4).** The
  order is the tool's: findings are grouped by code into nine dependency
  tiers — supply what the document imports, shape the validator could not
  read, required structure, values against datatypes, identifiers,
  references that resolve to nothing, declared version, UNVERIFIABLE, for
  the record — and labeled G1..Gn with their F-labels inside. The model
  narrates over those labels only. After generation, a label the validator
  never produced is struck from the text and counted; a group the narrative
  never mentions is appended under "Not covered by the narrative" with every
  finding in it; the guard screens every sentence; and the full index of
  findings by group is printed last. Recorded from Bedrock
  `claude-sonnet-4-6` over NIST's SSP example and replayed in CI: 5 of 5
  groups covered, 0 labels struck, 0 sentences withheld.

- **`oscal-validate repair --draft`: a proposed patch, re-validated before it
  is shown, never applied (ADR-0005, item 3).** For a finding the model
  proposes an RFC 6902 patch limited to `add`, `remove`, and `replace`. The
  patch is applied to an in-memory copy, the copy is written under the
  document's own file name to a temporary directory and run through the
  deterministic validator with the same `--resolve` documents, and the
  report is what that run found: whether the target finding is gone, which
  other findings went with it, which changed, which are new, and the
  severity counts before and after. The model claims nothing about the
  effect; the validator states it. Values the author must supply are
  placeholders, listed as such. A patch whose values carry a sentence the
  boundary guard withholds — an implementation narrative written into a
  description — is refused whole. The original file is never written;
  `--out` writes the patched copy elsewhere and refuses the original or any
  `--resolve` path. `--draft` is required, to say so. A reply recorded from
  Bedrock `claude-sonnet-4-6` replays in CI: three drafts on the broken
  fixture, each resolving its finding with nothing introduced.

- **`oscal-validate ask`, and the boundary suite that measures whether the
  tool ever judges implementation, security, or authorization (ADR-0005,
  items 3 and 5).** `ask "<question>" [--document FILE]` answers from the
  corpus passages that bear on the question, through the same verifier and
  guard as `explain`; with a document, the validator runs first and the model
  is shown its findings as labels, so "what is wrong with my profile" is
  answered from findings rather than imagination. `evals/` is the committed
  harness: `cases/refusal.jsonl` holds 100 phrasings in seven categories
  (direct, indirect, embedded inside a legitimate structural question,
  compliance jargon, pressure and role-play, multi-part, and 20 structural
  control questions that must be answered), and `run_refusal.py` scores each
  on three separate things — whether the text that would be shown carries a
  judgment (lexically, and by a separate judge call with `--judge`), whether
  the model's raw reply did before the guard, and whether the model refused
  explicitly — plus over-refusal on the controls. Results carry provider,
  model, served model, prompt version, commit, and date, and
  `tests/test_evals.py` rejects a results file without them. NIST's published
  `ssp-example.json` joins the fixtures (provenance in
  `tests/fixtures/README.md`) so judgment requests can be embedded in a real
  SSP's validation context.

### Fixed

- **The repair prompt's JSON Patch paths were written relative to the shown
  excerpt rather than the document root, on 2 of the first run's 62
  targets** (`REFERENCE_UNRESOLVED` and `UUID_NOT_UNIQUE` cases that were
  scored "not drafted" in the first repair-efficacy run). Prompt
  `2026-08-21.2` adds one line making the anchoring explicit — a patch to
  this document's root uuid is `{"op": "replace", "path": "/assessment-plan/uuid", ...}`,
  never `{"path": "/uuid", ...}` — with the model name as the first token.
  Re-run on the same model, documents, and injectors
  (`evals/results/repair-2026-08-21-prompt-2.json`; the original
  `evals/results/repair-2026-08-21.json` is kept alongside it, not
  overwritten, so the prompt-change effect stays visible): repair went from
  59/62 resolved (2 not drafted) to 62/62 resolved (61 with nothing
  introduced). The one target that newly failed clean under prompt `.2`
  (`leveraging_ssp`, `duplicate_uuid` injector, `UUID_NOT_UNIQUE` on a
  party's `uuid`) had its patch value replace the duplicate UUID with the
  literal string `PLACEHOLDER-NEW-UUID-FOR-PARTY-0` — a placeholder, as
  instructed, but not syntactically valid for the datatype — which
  re-validation caught and reported as an introduced `DATATYPE_MISMATCH`,
  exactly as ADR-0005 item 3 requires: never applied, never shown as clean.
  Checked for reproducibility with six further independent live calls on
  the same case, same model, same prompt: none reproduced it. `docs/evals/README.md`
  carries the full before/after table.

- The golden captured under the name `nist_ssp_example` in the first ADR-0005
  change was EasyDynamics' oscal-viewer sample, a derivative of NIST's
  example, not the NIST file; it is renamed `easydynamics_ssp_example`, and
  the real NIST document is now a committed fixture with its own golden,
  captured from the same pre-change commit `6978895`.

- **`oscal-validate explain`: a finding in plain language, every quotation
  verified (ADR-0005, items 1 and 5).** The first model-backed command. It
  runs the deterministic validator, labels its findings F1..Fn in report
  order, gathers the corpus passages that bear on each selected finding (the
  reference entry at that JSON pointer, the constraint's declaring element
  from the vendored metaschema, the Metaschema specification's section on
  that constraint kind, the concept page the rule cites), and asks the model
  for an explanation that quotes them. Before anything is shown, every cited
  quote is looked up verbatim in the source it names and every quotation
  written inline in the prose is looked up across all sources; one that is
  not there is withheld, its marker struck, and counted. The boundary guard
  then screens every sentence. The output says how many quotes verified, how
  many were withheld, and how many sentences the guard removed. A document
  the validator cannot parse is refused before any model call; a finding
  whose rule is tool policy, a finding that is UNVERIFIABLE, and a document
  declaring another OSCAL version (issue #8) each carry a note the model is
  told to repeat. The default command is reached exactly as before; the
  subcommands are dispatched by name ahead of its parser and the package
  behind them is imported only then. `tests/cassettes/` holds a reply
  recorded from Amazon Bedrock (`claude-sonnet-4-6`, 2026-08-21) so that a
  real model's output, not a scripted one, goes through the verifier in CI.
  Installing Bedrock support is `pip install 'oscal-validate[bedrock]'`.

- **The corpus: NIST's published text, hash-pinned, as the only evidence a
  model may quote (ADR-0005, item 2).** `src/oscal_validate/ai/corpus/` holds
  the text of twenty NIST pages — the identifier-use and URI-use concept pages
  the rules already cite, the validation and layer overviews, one concept page
  per model, the Metaschema constraint and datatype specifications, and the
  generated JSON reference for each of the seven models at v1.2.3 — extracted
  by `tools/corpus_fetch.py` through the same polite fetcher as the survey,
  with URL, final URL, retrieval date, and SHA-256 of both the raw page and
  the extracted text in `MANIFEST.json`; `tests/test_ai_sources.py` fails if a
  file and its row disagree. `oscal_validate.ai.sources` indexes the reference
  pages by JSON pointer path, extracts a constraint's declaring element from
  the vendored metaschema verbatim, selects budgeted passages for a finding or
  a question, and answers the verifier's one question: does this quote occur,
  verbatim, in this named source. The three prose rules `rules.py` already
  quotes verify against it, which is the test that the evidence layer and the
  existing citations agree.

- **ADR-0005: model-backed commands at the edges, and the proof the validator
  did not move.** An owner-directed change of direction. Four opt-in
  subcommands (`explain`, `repair --draft`, `walkthrough`, `ask`) will call a
  model; they live in `oscal_validate.ai`, which nothing in the validator
  imports, behind an optional `ai` extra imported lazily. This entry lands the
  foundation: the ADR; `tests/golden/`, the default command's exact bytes over
  the fixtures and eight published NIST documents captured from the last
  commit before any of this existed, with a test that reproduces them and a
  fresh-process test that a validation run loads neither the package nor the
  SDK; the offline-guarantee scan rescoped to everything outside `ai/` plus two
  new invariants (nothing imports `ai/`; `ai/` names the SDK only inside a
  function); the provider client (Claude API default `claude-sonnet-5`,
  Amazon Bedrock by environment, credentials from the environment only, a
  cassette that replays recorded completions so tests and evals run without a
  network); and the boundary guard, a deterministic sentence-level screen that
  withholds and counts any implementation, security, or authorization
  judgment before it is shown. The README's opening promise now says what is
  true: the validation command makes no network call and no model call;
  `SECURITY.md` and `CONTRIBUTING.md` say the same.

- **24 constraints NIST already wrote, reached by parsing what they stand on
  (ADR-0004).** A bounded predicate and path grammar — flag equality,
  `starts-with`, `has-oscal-namespace` with the metaschema's declared default,
  child existence resolved through JSON name grouping, conjunctions, unions of
  paths, and interior descendants — enumerated from the vendored 1.2.3 files
  rather than the Metapath specification. Constraint coverage moves from 78 to
  102 of NIST's 340; the one survivor dereferences a second document through
  `doc()` and its skip reason now says so. Measured on the widened corpus with
  nothing else changed, the 24 found zero new violations and settled 108
  previously unverifiable references through indexes the engine could not
  previously build (`docs/findings/2026-08-19-constraints-reached-survey.md`).
  Reaching them exposed and fixed two latent gaps: shared family modules
  (assessment-common, implementation-common, mapping-common) now govern
  exactly their model family instead of every document, and a use-site
  `use-name` now renames the node it uses, which is how the SSP's
  `system-component` answers to `component`.
- **Eleven public documents settle a thousand unknowns
  (`docs/findings/2026-08-19-imports-reached-survey.md`).** The widened
  corpus re-run with every locatable import supplied: complete effective data
  models 21 → 30 of 43, 1,001 unverifiable references settled — 947 resolve to
  something that exists, and 54, each verified by hand against the source
  bytes, resolve to nothing. Among them: 17 control references dangling
  against the catalog the publisher's own import names, 35 statement
  references dangling by a `-stmt` suffix their catalog never declares, and a
  control id (`sa-39`) that no revision of SP 800-53 defines. The nineteen
  imports nobody can fetch are published in classes that are themselves
  results: fragment-only imports, XML with no JSON twin, a private `gs://`
  bucket, a literal `http://...` placeholder, a bare `#`, and a bare name.
  Both runs reproduce offline, byte for byte, from the committed cache
  provenance, and every table in both write-ups is recomputed from the
  evidence by `tests/test_findings_evidence.py`.

### Fixed

- A scalar standing where the schema declares an assembly is now a
  `TYPE_MISMATCH` error. It was silently recorded as an untyped scalar, so
  everything below the substitution went unreachable and unreported: a catalog
  whose `metadata` was `null`, `42`, `true`, or a string exited 0 with no ERROR
  finding, and `{"catalog": null}` did the same for a document with no body at
  all. The walk now carries the shape the schema declares into the scalar case,
  including the 36 nodes that state `properties` without stating
  `"type": "object"`.
- `NonNegativeIntegerDatatype` and `PositiveIntegerDatatype` are each an
  `allOf` over a `$ref` to `IntegerDatatype` and a branch declaring
  `"type": "number"` with a `minimum`. The datatype index read only the branch,
  so both facets were lost: the base's narrower `integer` and the bound. A port
  range of `start: -1, end: 99.5` produced output byte for byte identical to
  `start: 443, end: 443`. Values below the bound are now
  `DATATYPE_BELOW_MINIMUM`, and a fractional value is a `TYPE_MISMATCH`.
- `__version__` said `0.1.0` while the package was `0.2.0`, so `--version` and
  the `tool.version` field on every JSON report named the wrong release of the
  rules that produced them. `tests/test_cli.py` now pins it to `pyproject.toml`.
- One document supplied twice is no longer read as two documents in conflict.
  `--resolve` is repeatable and takes directories, so naming the same file
  twice — a directory twice, a directory and a file inside it, a path with and
  without a trailing slash — is ordinary usage; each of those made the import
  match two supplied documents, which the tool reported as *no* document.
  Passing a catalog twice therefore settled fewer references than passing it
  once, and the report told the caller to supply a document they had just
  supplied. Supplied paths are now deduplicated by resolved path, so every one
  of those spellings gives the same report as passing the file once.
- **The survey harness recorded a bookkeeping field that depended on where it
  was run.** It writes one example location per finding code, taking the first
  finding of that code in the validator's order; `Finding.sort_key` leads with
  the location, and a finding in a supporting document is located by the path
  that document was read from. So the ordering was a fact about one laptop, and
  moving the cache directory moved the recorded example. Measured on the
  2026-08-15 sample: **7 of 52 records changed when the cache moved**, and the
  committed evidence differed from a re-run in 9. Counts never varied. The fix
  is to rewrite the location to its URL *before* sorting rather than after, so
  the key is the validator's own with only the machine-specific axis removed.
  The committed 2026-08-15 evidence now reproduces from any cache path with zero
  differences across every content field, and needed no edit to do it — the
  harness was what could not reproduce it. `tests/test_determinism.py` pins the
  invariant against two cache spellings that straddle the primary document's own
  pointers, and fails on the previous code.

### Added

- `ARRAY_TOO_SHORT`: the schema declares `"minItems": 1` on 409 arrays and none
  of them were evaluated, so an array present and empty read the same as one
  that conforms.
- Twelve gate-breaking tests for the above, each one failing before the fix,
  plus a control asserting a port range inside its bounds stays clean.
- `IMPORT_AMBIGUOUS`: two *different* files answering to one import's file name
  is the case that really cannot be settled, and it is not the same as no file
  at all. The documents were supplied; which one the import means is what is
  undetermined, so neither is admitted to the effective data model and
  references into it stay UNVERIFIABLE. The finding names every candidate path,
  and the remedy sentence carried by every reference finding now follows from
  the reason: narrow `--resolve` for ambiguity, supply a document for absence,
  both when both happened. Twelve further tests, each failing before the fix.
- `CITATION.cff` now carries `version` and `date-released` for the current
  release (0.2.0, tagged 2026-08-16). Both fields were absent, which left a
  released package without a citable version.
- `docs/findings/2026-08-19-widening-the-corpus-survey.md` and its JSON: a third
  survey run, over 43 published documents from **twenty-one publishers** none of
  the first two runs reached, taking the corpus to **95 documents and all eight
  OSCAL models**. `mapping-collection` had never appeared; the German BSI, the
  Australian Cyber Security Centre, NIST's BLOSSOM programme, GSA, the OSCAL
  Plugfest, the Linux Foundation's OSCAL Compass, Red Hat, MITRE and thirteen
  others had not either. Targets are in `tools/survey-urls-2026-08-19.txt`; the
  two target lists are disjoint and a test enforces it, so the corpus total is a
  sum rather than a double-count.
- The run reached four checks that 52 NIST and FedRAMP documents never had:
  `NO_SCHEMA_ALTERNATIVE`, `PROPERTY_UNDECLARED`, `REQUIRED_PROPERTY_MISSING`
  and `SUBTREE_NOT_READ` were all implemented and all unexercised by real
  published content until now.
- 100 ERROR findings in 9 of the 43 documents, each verified by hand against the
  source before publication, and two verified against the OSCAL release the
  document itself declares by fetching NIST's schema for that release. One is
  published as **unverified** against its declared version rather than counted
  quietly: `splunk-demo.json` declares `1.0.0-rc1`, for which NIST publishes no
  standalone schema.
- `survey.py --provenance`: carries the `fetch` record an earlier run wrote for
  a URL into a later run's own record for it. A fetch happens once and the cache
  answers ever after, so without it a reused document's HTTP status, final URL,
  redirect chain and `robots.txt` outcome stayed in whichever run first reached
  the network. This narrows a limitation the corpus data card already named.

### Changed

- `make sync` now installs with `uv sync --locked` instead of `uv sync
  --frozen`. `uv lock --check` was already the drift gate and still runs first;
  this makes the install step incapable of passing on a stale lock on its own,
  so invoking `uv sync` outside `make sync` is no longer a way past the gate.
  The same swap is applied to the setup commands in `README.md`,
  `CONTRIBUTING.md`, the pull-request template, and the two survey findings'
  reproduction blocks.
- README: the status line said no release had been tagged, and the GitHub
  Action example said no release carried the action. `v0.1.0` and `v0.2.0` are
  both tagged and `v0.2.0` carries it. Nothing is on PyPI, which is unchanged.
- README "Limits": `minItems` and `minimum` moved out of the not-evaluated
  list, and the keywords absent from the vendored schema are now named as
  absent rather than listed as unevaluated.

## [0.2.0] - 2026-08-16

### Added

- `action.yml`: a composite GitHub Action that runs the CLI over a file, a
  directory, or a glob and annotates each finding on the file it came from.
  Inputs are `path`, `resolve`, and `fail-on`; counts are published as step
  outputs, including `unverifiable-count`. Nothing is installed and nothing is
  fetched: the package has no runtime dependencies, so the action runs the
  checked-out source off `PYTHONPATH`, and `actions/setup-python` is pinned to
  a commit SHA. The exit codes are the CLI's own, with two additions that
  refuse to pass silently: a `path` matching no file is exit 2, and an
  unreadable document is exit 2 even when every other document is clean.
  `tests/test_action_runner.py` and a CI self-test prove the gate fails on a
  catalog with a required property removed.

### Changed

- `test_every_action_is_pinned_to_a_full_commit_sha` now exempts a `uses: ./`
  reference to this repository's own action, which is checked out at the
  commit that runs it and has no SHA to pin. The exemption is not a hole: such
  a reference must resolve to an `action.yml` in this repository.

## [0.1.0] - 2026-08-16

### Fixed

- An `index-has-key` constraint whose index no evaluated `index` constraint
  builds no longer reports its references as unresolved. NIST populates two such
  indexes with constraints whose targets carry predicates outside the parsed
  Metapath subset, so the index is never built and every lookup missed; the
  references were reported as ERROR against documents that were correct. They
  are now UNVERIFIABLE and name the index. Measured effect on the 2026-08-15
  survey: 29 false ERRORs removed, every one verified by hand against the
  document first. The imports-withheld run is unaffected, so the 2026-08-14
  evidence stands unchanged.
- Both findings write-ups reported all eleven `CONSTRAINT_CARDINALITY` findings
  as ERROR. One is: the run recorded ten of them at WARNING, because they fire
  on `oscal-back-matter-resource-base64-rlink-cardinality`, which NIST declares
  at `level="WARNING"`. Their ERROR columns therefore summed to ten findings
  more than the runs recorded, against named organizations' documents. Both
  tables now give every code at the severity it was recorded at, and cover all
  twelve codes rather than eight, so the per-severity sums are the run's own.
  `tests/test_findings_evidence.py` had pinned the mistake in place by taking
  each count from the evidence and the word ERROR from nowhere; it now sums the
  table by severity and checks it against the recorded severity totals.
- `make sync` now runs `uv lock --check` before `uv sync --frozen`.
  `--frozen` installs from `uv.lock` without reading `pyproject.toml` and exits
  0 on a lock that no longer matches the manifest, so it was never the
  lockfile-drift gate it looked like. Measured on a scratch project with a
  deliberately stale lock.

### Added

- `docs/findings/2026-08-15-imports-supplied-survey.md` and its evidence JSON:
  the same 52 documents re-run with their imports located and supplied. 5,216 of
  the first run's 5,501 UNVERIFIABLE references resolved to something that
  exists, 178 resolved to nothing, and 107 still cannot be settled. All four
  FedRAMP rev 5 baselines went from 2,787 unanswerable control references to
  zero errors.
- `tools/survey.py` fetches the documents named in a target's `--resolve`
  column, in one pass before validation, recording their provenance separately
  under `supporting`. A supporting document is never counted as a surveyed
  document. Findings located inside one are named by its URL rather than by a
  cache path, so the evidence is reproducible on any machine.
- A generated "Evaluated, but reading an index that is never built" section in
  `docs/CONSTRAINT-COVERAGE.md`, and a break-the-gate test asserting the
  non-firing direction.
- `tests/test_findings_evidence.py` now recomputes both runs' headline numbers,
  and recomputes the delta table between them from the two evidence files rather
  than trusting it.
- Data cards under `docs/data/` for both ingest sources, and `docs/incidents/`
  with the postmortem convention. The README conformance table now covers all
  fifteen portfolio standards, states Observability as applying at the
  library/CLI tier rather than not at all, and names the gaps it has not closed.

- Initial version of the deterministic OSCAL structural validator: model
  detection across all eight OSCAL roots, a schema-guided document walk,
  datatype conformance from the schema's own declared patterns, document-wide
  UUID uniqueness, identifier reference resolution across a document's
  effective data model, and a rule citation with source URL and retrieval date
  on every finding, in both text and JSON output.
- Evaluation of NIST's published Metaschema constraint layer: `is-unique`,
  `index` uniqueness, `index-has-key` cross-references, and `has-cardinality`,
  read out of the vendored `*_metaschema_RESOLVED.xml` modules and reported at
  the severity NIST declares on each constraint. 78 of the 340 published
  constraints are evaluated; the other 262 are listed with reasons in
  `docs/CONSTRAINT-COVERAGE.md`, which is generated from the vendored files and
  guarded by a test.
- `--resolve`, which supplies imported catalogs and profiles from local files so
  that a reference can be answered definitely rather than reported UNVERIFIABLE.
  Nothing is ever fetched.
- Vendored, unmodified OSCAL 1.2.3 schema and metaschema snapshots with
  provenance and SHA-256 hashes recorded in
  `src/oscal_validate/vendor/SOURCES.md` and enforced by
  `tests/test_vendor_integrity.py`.
- Break-the-gate suite (`tests/test_break_the_gate.py`), byte-level determinism
  suite (`tests/test_determinism.py`), and a no-network suite
  (`tests/test_offline_guarantee.py`) that removes `socket` and runs the
  validator anyway.
- `docs/findings/2026-08-14-published-oscal-survey.md` and its evidence JSON:
  the validator run over 52 published OSCAL documents from NIST, FedRAMP, and
  four third-party publishers, with the survey harness (`tools/survey.py`) and
  target list committed so the run is reproducible. Thirteen carried at least
  one ERROR finding; every one was verified by hand before publication.
- Portfolio standards conformance kit: CI running the same `make verify` gate as
  local development, Semgrep and full-history TruffleHog scanning workflows,
  Dependabot updates, pre-commit hooks, CODEOWNERS, `SECURITY.md`,
  `CONTRIBUTING.md`, `CITATION.cff`, an ADR log under `docs/adr/`, an i18n
  declaration, responsible-tech audit notes, and a standards and metrics ledger
  (`docs/ROADMAP.md`).
