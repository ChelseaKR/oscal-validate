# Reaching the constraints NIST already published

Status: active. Written 2026-08-28. Owner: Chelsea Kelly-Reif.

This plan covers roughly two to three years of work on one subject: the 238
constraints NIST publishes in the vendored metaschema modules that this tool
does not evaluate. It is subordinate to `CONTRIBUTING.md` and to the ADRs.
Nothing in it authorises encoding a rule from memory, guessing at a Metapath
expression, or letting an unevaluated constraint report as a pass.

`docs/ROADMAP.md` is the enforcement ledger for gates and metrics. This file is
the feature arc, and it exists because the single largest honest statement in
this repository is a number in a generated table:

> 102 of 340 published constraints are evaluated.

Every one of the other 238 is NIST's, is already vendored, is already
hash-pinned, and needs no network call and no new source to reach. That is the
whole opportunity, and it is why this plan has phases rather than ideas.

## The bar every phase clears

1. **No invented rule.** A constraint is evaluated by reading the vendored
   `*_metaschema_RESOLVED.xml` file that declares it, at the `level` NIST
   declares on it. Semantics for a constraint kind come from the vendored
   Metaschema specification text in `src/oscal_validate/ai/corpus/`, which is
   hash-pinned by `tests/test_ai_sources.py`, quoted rather than paraphrased.
2. **Sized by evidence, not by specification.** ADR-0004 set the method: a
   grammar is enumerated from the shapes the vendored files actually use, never
   from what Metapath permits. A shape outside the enumeration returns nothing
   and the constraint stays reported as not evaluated, with its reason.
3. **Under-selection is a defect, not a partial success.** A target that
   selects fewer nodes than NIST wrote accuses conforming documents or excuses
   defective ones. Where completeness cannot be proved, the answer is not
   evaluated, never a finding.
4. **Fail closed.** Nothing this plan adds may turn an UNVERIFIABLE into a
   silent pass, and every new evaluation path arrives with a case in
   `tests/test_break_the_gate.py` that produced zero ERROR before it.
5. **The coverage table is generated.** `docs/CONSTRAINT-COVERAGE.md` comes out
   of `tools/constraint_coverage.py`. No phase hand-edits it, and every phase
   moves its numbers or explains why it did not.
6. **Offline stays offline.** Nothing here touches
   `tests/test_offline_guarantee.py` or the byte-identity goldens except where
   a phase deliberately moves output, and then it says so and re-records.

## What is actually in the gap

Measured from the vendored 1.2.3 modules, not from impression:

| Kind | Published | Evaluated today | What blocks the rest |
|---|---:|---:|---|
| `is-unique` | 48 | 48 | nothing |
| `index-has-key` | 24 | 24 | nothing |
| `has-cardinality` | 11 | 11 | nothing |
| `index` | 20 | 19 | one `doc()` target |
| `matches` | 25 | 0 | value targets, then regex and datatype application |
| `expect` | 12 | 0 | a boolean `@test` grammar |
| `allowed-values` | 200 | 0 | value targets, then the applicable-set rule |

Three measurements sharpen that table, and each is the reason a phase exists.

**The published reason for skipping `allowed-values` is wrong.** The tool
records one blanket reason for all 200: "most allowed-value sets declare
allow-other, so a value outside them is not necessarily a violation". Counted
in the vendored files, 60 of 200 declare `allow-other` and 140 do not. The
vendored Metaschema specification settles which way the default runs:

> no: (default) Identifies the expected value set as closed. This is the
> implicit default value if no @allow-other is provided.

and settles what a mixed applicable set means:

> One <allowed-values> constraint in the applicable set MUST have the
> @allow-other attribute value no. The expected value set is closed.

So the published record says the opposite of what this repository publishes
about it. Phase 1 fixes the statement; Phase 4 acts on it.

**Value targets are the shared blocker.** `allowed-values` and `matches`
constrain the value of a field or a flag, so their targets end in a flag step
(`prop[...]/@name`, `@resource-fragment`) or select the context node's own
value (`.`). The parser has no flag step, so 155 of 200 `allowed-values`
targets and 18 of 25 `matches` targets fail to parse for that reason alone.
This is one grammar addition serving two kinds, which is why it is its own
phase and comes before both.

**`expect` is blocked only on its test.** All 12 `expect` targets already parse
under the ADR-0004 grammar. What is missing is a boolean evaluator for
`@test`, and the 12 published tests use a small enumerable set of forms.

---

## Phase 1: say why, per constraint

**Delivers.** The reason a constraint is not evaluated is computed from what
that constraint declares, not looked up by kind. An `allowed-values` set that
declares `allow-other="yes"` says so; one that does not says that its set is
closed by the published default and names what is still missing. A `matches`
constraint says whether it is blocked on its target, its regex, or a datatype
the vendored schema does not define.

**Depends on.** Nothing.

**Done when.** No reason in `docs/CONSTRAINT-COVERAGE.md` is a per-kind
constant; a test derives the expected reason for every unevaluated constraint
from the vendored files and fails if the published reason disagrees; the
README's Limits section states the counted split rather than "mostly"; the
evaluated count is unchanged, because this phase changes no verdict.

## Phase 2: value targets

**Delivers.** The target grammar gains the two shapes a value constraint needs
and nothing else: a terminal flag step (`.../@name`, or a bare `@name`, which
the specification says is the flag's own value) and the context node's value
(`.`). Selection returns the value at that position, distinguishing a flag that
is absent from a flag whose value is null.

**Depends on.** Phase 1, so that the reasons the new parse status feeds are
already per-constraint.

**Done when.** The counted number of `allowed-values` and `matches` targets
that parse is pinned by a test; no constraint becomes evaluated by this phase
alone, because parsing a target is not evaluating a constraint; the coverage
table's reasons narrow from "its target expression is outside the subset" to
the real remaining blocker for each.

## Phase 3: `matches`

**Delivers.** `matches` constraints evaluated at NIST's declared level. A
`@regex` is applied as published. A `@datatype` is applied by resolving the
metaschema datatype name onto the vendored JSON Schema's datatype definition
and using the pattern that definition already carries, which is the same
pattern check 2 applies. The correspondence is mechanical, both names
lowercased with hyphens removed, and total: a name that does not resolve to
exactly one vendored definition is not evaluated, and says so.

**Depends on.** Phase 2.

**Done when.** Every `matches` constraint is either evaluated or carries a
reason naming which of the three blockers applies; the three datatypes the
vendored schema does not define (`date-time`, `ip-v4-address`, `ip-v6-address`)
and the datatypes it defines without a pattern are reported as such rather than
approximated; `tests/test_break_the_gate.py` gains a seeded corruption per
evaluated constraint shape, each shown producing zero ERROR before.

## Phase 4: `allowed-values`, where the applicable set is provably complete

**Delivers.** The two-phase evaluation the specification describes: resolve the
applicable set of `allowed-values` constraints for each target value node, then
evaluate the value against that set. Closed when any member of the set declares
or defaults to `allow-other="no"`; the permitted values are the union of the
enums across the whole set.

**The hard part is completeness, not comparison.** A value judged against a
partial applicable set is a false ERROR against a conforming document, which is
the exact failure this tool exists to avoid. So a value node is judged only
when the tool can prove it holds every `allowed-values` constraint that reaches
it. Where any `allowed-values` target in the same model failed to parse, the
set cannot be proved complete and the affected nodes are reported not
evaluated, naming the constraint whose target was not read.

**Depends on.** Phase 2, and on Phase 1 having published the corrected reason.

**Done when.** An ADR records the applicable-set rule with the specification
quoted; completeness is a computed property with a test, not an assumption;
a document whose value is outside a proved-closed set produces an ERROR at
NIST's level, and the same document with an unparsed sibling constraint
produces a not-evaluated report instead; no published NIST document in the
corpus gains a finding that is not verified by hand against the vendored
module that declares the constraint.

## Phase 5: `expect`

**Delivers.** A boolean `@test` evaluator, enumerated from the 12 published
tests exactly as ADR-0004 enumerated the predicate grammar: flag existence
(`@uuid`, `exists(@start)`), negation of existence, child existence, flag
equality, an ordering comparison between two flags, and a top-level `or`.
Anything outside the enumeration evaluates to nothing and the constraint stays
reported as not evaluated.

**Depends on.** Phase 2 for value access. The 12 targets already parse.

**Done when.** Each of the 12 is evaluated or carries its own reason; the
grammar's boundary is asserted by tests that feed it forms from outside the
enumeration and require refusal, not a guess; break-the-gate cases exist for
each evaluated form.

## Phase 6: the target shapes that remain

**Delivers.** The `allowed-values` targets Phase 2 still cannot read, which are
the reason Phase 4 has to withhold judgment on parts of the SSP and the
assessment models: a parenthesised context step carrying predicates
(`(.)[@type='software']/...`), interior unions (`(.|statement|.//by-component)/...`),
and a top-level union whose alternatives end in flag steps. Each shape is
enumerated from the vendored files first and implemented only if the
enumeration is closed.

**Depends on.** Phase 4, because the value of this phase is measured in
applicable sets that become provably complete.

**Done when.** The count of `allowed-values` targets that parse is pinned
higher by a test; the coverage table shows the movement; every shape that is
still declined is named individually rather than by category; Phase 4's
completeness gate opens for the models the new shapes finish.

## Phase 7: what only the owner can decide

Carried here so it is not mistaken for work that is merely undone. Each item is
recorded in `docs/ROADMAP.md` under open review and owner actions, and none of
them is a coding task:

- Whether to implement profile resolution, which is the precondition for
  checking `by-id` and `objective-id` references at all.
- Whether to implement `doc()`, the one remaining `index` target.
- How a document declaring an older `oscal-version` should be reported.
- Whether `--log-format json` is implemented or declared not applicable.
- Whether to publish to PyPI, and whether to add a release workflow.
- The repository settings that cannot be changed from inside the repository:
  branch protection on `main`, private vulnerability reporting, and the
  incident labels.

---

## Sequencing

| Order | Phase | Depends on | Constraints it can reach |
|---|---|---|---:|
| 1 | Say why, per constraint | nothing | 0, by design |
| 2 | Value targets | 1 | 0, by design |
| 3 | `matches` | 2 | up to 25 |
| 4 | `allowed-values` | 2 | up to 200 |
| 5 | `expect` | 2 | up to 12 |
| 6 | Remaining target shapes | 4 | widens 4 |
| 7 | Owner decisions | people | not code |

Phases 3, 4 and 5 are independent of each other and can land in any order.
Phase 6 is worth doing only after Phase 4 shows where completeness is blocked.

## Refused, and staying refused

- **A general Metapath implementation.** The bounded grammars here exist
  because a partial evaluator that guesses is worse than one that declines.
  ADR-0004 records the reasoning and this plan does not reopen it.
- **Approximating a datatype the vendored schema does not define.** Writing a
  pattern for `ip-v4-address` from knowledge of what an IPv4 address looks like
  is a rule encoded from memory, which is the one thing this tool refuses.
- **Judging a value against a partial applicable set.** Covered above; it is
  the failure mode Phase 4 is shaped around.
- **Raising or lowering NIST's declared level.** A constraint declared
  `WARNING` produces a WARNING even where a stricter reading would call it an
  error, because the published level is part of the published rule.
