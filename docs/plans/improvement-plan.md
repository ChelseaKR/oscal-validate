# Improvement plan: every finding code needs a witness

Audit date: 2026-08-28. Baseline: `main` at `8e50425`, `make verify` green,
415 tests, 94.59% coverage.

The governing rule for this pass is that a check which cannot fail is worse
than no check. Everything below was measured against the tree, not read off
the documentation.

## What the audit measured

### The census

Every finding code the package can emit was enumerated from the source by AST
rather than by regular expression: every `Finding(...)` call site, with the
`code=` keyword resolved through conditional expressions and through local
names assigned literals in the same function. That is 19 codes. A `[A-Z_]+`
regular expression would have found the same 19 here, but only by luck: the
three `IMPORT_*` codes reach the constructor through a variable, and nothing
guarantees a future code is spelled without a digit.

The suite was then instrumented to record every code actually constructed
during a full `pytest` run. Seventeen of the nineteen appeared. Two did not:

| Code | Emitted at | Reachable? | Exercised by any test? |
|---|---|---|---|
| `CONSTRAINT_CARDINALITY` | `checks/constraints.py` | yes | no |
| `SUBTREE_NOT_READ` | `checks/structure.py` | yes, by one of four paths | no |

Both are listed in the README's "What it checks" table. Both survive the 90%
coverage floor because the modules around them are otherwise well covered:
`checks/constraints.py` is at 89% and `checks/structure.py` at 94%, and the
uncovered lines are exactly these two emit sites.

`CONSTRAINT_CARDINALITY` is not theoretical. All 11 of NIST's
`has-cardinality` constraints parse and are evaluated. Removing `rlinks` from
the clean catalog's one back-matter resource produces it at WARNING, which is
the level NIST declares on
`oscal-back-matter-resource-base64-rlink-cardinality`. Adding a `location`
carrying none of title, address, email-address or telephone-number produces it
at ERROR, from
`oscal-metadata-location-title-address-email-address-telephone-cardinality`.

`SUBTREE_NOT_READ` is reachable too, but by fewer routes than the repository
claims. See below.

### ADR-0007 overstates why `SUBTREE_NOT_READ` is not dead code

ADR-0007 says:

> `SUBTREE_NOT_READ` remains reachable and is not dead code: it still reports
> an array with no declared item shape, object alternatives that disagree
> about what a property means, and object alternatives where the value is not
> an object.

Measured against the vendored OSCAL 1.2.3 schema:

| Reason | Emit site | Sites in the vendored schema |
|---|---|---|
| a union shape the resolver declines | `document.py:183` | 0 reachable from a model root (already pinned by `test_no_document_shape_in_the_vendored_schema_is_left_unresolved`) |
| an array with no declared item shape | `document.py:252` | 0 — no node anywhere in the schema declares `"type": "array"` without a dict `items` |
| alternatives that disagree about a property | `document.py:352` | 0 — of the 13 branch sites in `definitions`, none has two alternatives declaring one shared property differently |
| alternatives where the value is not an object | `document.py:337` | 98 branch sites; reachable from any document |

So one of the four routes is reachable against 1.2.3, not three. The ADR's
sentence is a claim about reachability with no measurement behind it, and it
happens to be right about the conclusion for the wrong reasons. The fix is to
say what was measured and to add the test that makes the conclusion checkable.

### A test that promises to fail and cannot

`tests/test_findings_evidence.py::test_the_unread_mapping_subtree_is_reported_on_every_mapping_collection`
carries this docstring:

> If a future change makes the walker resolve that subtree, this test fails and
> the write-up has to be corrected rather than left claiming a limit that is no
> longer there. A stale limitation is as misleading as a stale number.

That change landed in #25 (ADR-0007). The walker now resolves
`/mapping-collection/mappings`, `oscal-validate tests/fixtures/clean_mapping_collection.json`
reports no `SUBTREE_NOT_READ` at all, and the test is still green — because it
reads the frozen `docs/findings/2026-08-19-widening-the-corpus-survey.json`
and not a live run. Pinning the historical record is a legitimate thing for
that test to do. Promising to notice a behaviour change it cannot observe is
not.

### A stale pointer

`checks/references.py` says `IDENTITY_TITLES` is "pinned by
tests/test_reference_titles.py". No such file exists. The pinning is real and
lives in `tests/test_schema_and_walk.py`.

### A gate that would pass over an empty directory

`tests/test_security_policy.py::test_every_action_is_pinned_to_a_full_commit_sha`
iterates `WORKFLOWS.glob("*.yml")` and asserts inside the loop. A renamed
directory, or a workflow written as `.yaml`, yields nothing to assert and a
green test. The workflows are the only thing pinning third-party actions to a
commit SHA, so this one has to say how many files it read.

### Named traps checked and found already handled

Recorded so a later reader knows the ground was covered.

- `gitleaks detect --source .` does not appear. gitleaks runs diff-scoped
  through pre-commit, and whole-history scanning is TruffleHog's job in
  `trufflehog.yml` with `fetch-depth: 0`.
- `uv sync --frozen` is not a gate here and the Makefile says why at length.
  `make sync` is `uv lock --check` followed by `uv sync --locked`.
- `semgrep test` does not appear. `semgrep ci --config auto` scans the whole
  checkout; no path is excluded, and `tests/test_security_policy.py` fails if
  `--exclude` appears.
- mypy's `files` covers `src`, `tests`, `tools` and `evals`; ruff runs over
  `.`. The gate scripts are inside the linted and type-checked scope.
- `tools/action_runner.py` treats a `path` that matches no file as exit 2,
  with the reason stated in the message, and `tests/test_action_runner.py`
  asserts it.
- No shell `for` loop and no `cmd && cmd2 || echo` construct exists in any
  workflow, the Makefile, or the composite action.
- The two-sided numeric assertions in `tests/test_findings_evidence.py` are
  differences between two recorded runs and can go negative, so they can fail.
- `tests/golden/*.out` is generated by `tests/golden/capture.py` from the
  implementation, which would be circular for a conformance suite. It is not
  one: it is a regression pin captured at `6978895` and its purpose is to
  detect movement, which is exactly what a self-generated expectation can do.

### One thing left for the owner, and now decidable

`docs/ROADMAP.md` carries "Re-record `tests/cassettes/walkthrough-nist-ssp.json`"
as an owner action, blocking the correction of the `allowed-values` skip
summary. The entry says it is "a live billed call on the owner's Bedrock
account" without saying how many, or what else moves. Both were measured by
patching the sentence and replaying every cassette; the numbers are in
[the ROADMAP entry](../ROADMAP.md) as amended by this plan.

## Phases

Each phase is a commit, and every new assertion was broken deliberately before
being trusted.

1. **`tests/test_finding_code_census.py`.** Enumerate the codes by AST; assert
   the enumeration matches a declared roster; assert every code in the roster
   is emitted by a witness the test itself runs. A new code with no witness
   fails the gate.
2. **Gate-break cases for the two unexercised codes**, in
   `tests/test_break_the_gate.py`, each with the clean counterpart that proves
   the check is not reporting everything.
3. **`SUBTREE_NOT_READ` reachability, measured.** A test that reads the
   vendored schema and pins the count of sites behind each of ADR-0007's four
   reasons, and an amended ADR that says what was measured.
4. **The frozen-evidence test says what it pins**, with a live counterpart
   asserting the walker's behaviour today.
5. **Small corrections**: the stale `test_reference_titles.py` pointer, and
   the workflow glob that would pass over an empty directory.
6. **The Bedrock re-record, made decidable** in `docs/ROADMAP.md`.

## Not done here, and why

- **PR #27 (`feat/say-why-per-constraint`) does not compile.**
  `src/oscal_validate/metaschema.py` on that branch raises
  `SyntaxError: unmatched ')'` at line 660, from duplicated function-signature
  lines that look like a conflict resolved twice. Both `verify` and
  `action self-test` are red on it. PRs #28, #30 and #31 describe themselves
  as stacked on it and are all green, so the corruption is in that branch
  alone. It is in-flight owner work and is reported rather than rewritten.
- **Issue #8** (an ERROR against 1.2.3 is not always an ERROR against the
  declared version) asks for a decision between four options, one of which is
  "leave it and record why in an ADR". That is an owner decision about scope,
  not a defect to fix.
- **Issue #20** (redaction or fixtures-only mode) is marked by its own text as
  recorded future scope, not being built now.
- **Semgrep and TruffleHog run in CI with no `make` target**, so `make verify`
  can be green on a tree CI rejects. Closing that means installing both in the
  local toolchain, which is a real cost against a real benefit and is an owner
  call rather than a defect.
