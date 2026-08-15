# 1. Vendor both the JSON Schema and the Metaschema constraint layer

## Status

Accepted

## Context

Most OSCAL validation is JSON Schema validation, and NIST publishes a JSON
Schema per model plus a combined one. That schema expresses shape and datatypes
and nothing else: checked against the vendored 1.2.3 complete schema,
`uniqueItems`, `const`, `if`, `not`, and `dependentRequired` appear zero times.
It cannot express that two controls must not share an id, or that a link's `#`
fragment must name something that exists.

Those rules are published. They live in the Metaschema constraint layer that
NIST ships alongside the schema in the `*_metaschema_RESOLVED.xml` release
artifacts: 340 constraints in OSCAL 1.2.3, in seven kinds, each with a declared
severity level. A validator that read only the JSON Schema would be checking the
smaller half of the specification and would have no way to say so.

Reading them requires a Metapath evaluator, and Metapath is a full expression
language. A partial implementation that guessed at expressions it did not
understand would be worse than none.

## Decision

- Vendor both layers: `oscal_complete_schema.json` and all thirteen
  `*_metaschema_RESOLVED.xml` modules, unmodified, with source URLs, retrieval
  dates, and SHA-256 hashes recorded in `vendor/SOURCES.md` and enforced by
  `tests/test_vendor_integrity.py`.
- Implement a **bounded** Metapath subset (`.`, `name`, `a/b`, `a|b`,
  `//name`, `.//name`, `//(a|b|c)`) and evaluate the constraint kinds that
  subset can serve: `is-unique`, `index`, `index-has-key`, `has-cardinality`.
- Every constraint the tool does not evaluate is recorded with its reason,
  surfaced as an UNVERIFIABLE finding, and published in a generated coverage
  table that a test keeps current.
- Constraint findings carry the severity NIST declares on the constraint, not
  one this tool chooses.
- Apply a constraint only to documents of the model its module governs.
  Assembly names repeat across models: an SSP and a component definition each
  define `implemented-requirement`, with different rules.
- The package has zero runtime dependencies and performs no network calls.

## Consequences

- The tool evaluates 78 of 340 published constraints. That number is published
  rather than hidden, and it is the honest answer to "is a clean run
  conformance?" (no).
- Refreshing means re-vendoring fourteen files, re-recording their hashes, and
  regenerating the coverage table: a visible, reviewable diff.
- The bounded Metapath subset can be widened later without changing the
  citation model, because every constraint already carries its own target
  expression and reason.
- A constraint whose target expression uses a predicate cannot be evaluated at
  all today, which includes several of the back-matter link checks. Those are
  reached instead by the prose-rule reference check, which is cited separately.
