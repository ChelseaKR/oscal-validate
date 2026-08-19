# 4. A bounded predicate grammar, sized by the vendored files

Date: 2026-08-19

## Status

Accepted

## Context

25 of NIST's published constraints were skipped for one reason only: their
Metapath target expressions carry predicates or interior descendants, and the
target parser refused anything it did not understand. Those 25 are constraints
this tool already knows how to evaluate — `index`, `index-has-key`,
`has-cardinality` — at NIST's declared severities. The blocker was the
selector, not the rule (issue #1).

The repository's standing rule applies: a check that cannot be implemented
correctly is left out and named, never shipped approximate. A predicate parser
that guessed at a target would be worse than one that declines, so the grammar
had to be sized by evidence rather than by the Metapath specification.

## Decision

The predicate shapes were enumerated from the vendored 1.2.3
`*_metaschema_RESOLVED.xml` files — every distinct form across the 25 targets,
not a form the specification permits:

- `[@flag='value']` and `[@flag=('v1','v2',...)]` — a flag equal to one of a
  set of strings (`component[@type='service']`, `link[@rel=('related',
  'required','incorporated-into','moved-to') ...]`);
- `[starts-with(@flag,'prefix')]` — in the files, always `@href` against `#`;
- `[has-oscal-namespace('uri')]` and `[has-oscal-namespace(('uri1','uri2'))]`
  — true when the node's `ns` flag is in the set, where an absent `ns` means
  the default `http://csrc.nist.gov/ns/oscal`, as the metaschema declares;
- `[child-name]` — the named child selects at least one node
  (`responsible-role[party-uuid]`), resolved through the same JSON
  name-grouping the rest of selection uses, so `party-uuid` finds
  `party-uuids` and an empty array is zero nodes;
- conjunctions of the above with `and`;
- top-level unions of full paths (`responsible-role|statement/responsible-role
  |.//by-component//responsible-role`), evaluated as a union **deduplicated by
  location**, because the alternatives overlap and a node reached twice must
  be one entry in a uniqueness index and one occurrence in a cardinality
  count;
- interior descendants (`implemented-requirement//by-component/export/
  provided`).

Everything outside that enumeration still returns `None` and the constraint
stays `CONSTRAINT_NOT_EVALUATED` with its reason: disjunction with `or`,
negation, positional predicates, wildcards, axes, other functions — and
`doc()`. A union any alternative of which cannot be parsed is refused whole,
because evaluating a subset of a union changes what the constraint counts:
an under-selected `has-cardinality` minimum would accuse a conforming
document.

Exactly one previously blocked constraint remains declined:
`oscal-ssp-by-component-uuid-index`, whose target dereferences a second
document through `doc(...)`. Its skip reason now names that. The
`index-has-key` that reads its index stays evaluated and stays UNVERIFIABLE,
per ADR-0002, and `tests/test_break_the_gate.py` pins that direction.

Two consequences were accepted deliberately:

1. **Coverage moves from 78 to 102 of 340** without inventing a single rule;
   every unlocked constraint is NIST's, at NIST's level, already vendored and
   hash-pinned. `docs/CONSTRAINT-COVERAGE.md` is regenerated and the counts
   are pinned in `tests/test_metaschema.py`.
2. **Module scoping had to become model-set scoping.** The first newly
   reached constraints exposed a latent misapplication: `assessment-common`
   declares a cardinality constraint on a context named `part`, and a
   catalog's `part` is control-common's, not assessment-common's. Shared
   modules that serve one family now govern exactly that family
   (`assessment-common` → the three assessment models, `implementation-common`
   → SSP and component definition, `mapping-common` → mapping collection);
   `metadata` and `control-common` still govern every model.

## Consequences

The `Step` dataclass carries predicates; a parsed target is a union of paths.
A quoted string in the grammar must be one whole quoted string — an embedded
quote (`'a' or @name='b'`) is refused, not read as a value, which is the
parser refusing to turn a disjunction into an equality. Anything the grammar
declines is still reported, per constraint, with its reason, and the one
remaining `doc()` decline is named in the README's Limits.
