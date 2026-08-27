# 7. Resolve "one mapping or an array of mappings", and read the eighth model

Date: 2026-08-27

## Status

Accepted

## Context

OSCAL has eight models. Seven of them were checked. The eighth,
`mapping-collection`, produced this on every document in the corpus and on
every document anywhere:

```
UNVERIFIABLE SUBTREE_NOT_READ  at=/mapping-collection/mappings
```

`/mapping-collection/mappings` is the whole substance of a mapping collection:
the source controls, the target controls, and the relationship asserted between
them. Everything the tool checked in those documents was metadata, provenance
and back matter. The behaviour was correct and is what ADR-0002 asks for, but
it left one model with no gate to break, which by this repository's own rule
means one model whose checks were being trusted on faith
([issue #7](https://github.com/ChelseaKR/oscal-validate/issues/7)).

**Sized from the vendored file, not from impression.** The issue asked for the
blocking shapes to be enumerated the way ADR-0004 enumerated the predicate
shapes. Enumerated over every `allOf`/`anyOf` node in the vendored
`complete_schema.json`, the resolver declines four, and three of them are
datatype definition bodies the walk never hands it, because a `$ref` to a name
ending in `Datatype` resolves to the datatype itself. Exactly one declined node
is reachable from a model root:

```
#/definitions/oscal-complete-oscal-mapping:mapping-collection/properties/mappings

{"anyOf": [{"$ref": X},
           {"type": "array", "minItems": 1, "items": {"$ref": X}}]}
```

where X is `oscal-complete-oscal-mapping-common:mapping` in both branches.

**Why it occurs exactly once.** The vendored metaschema modules answer that.
The thirteen of them declare 394 `group-as` elements between them, and 393
carry `in-json="ARRAY"`. One does not:

```xml
<assembly ref="mapping" min-occurs="1" max-occurs="unbounded">
   <group-as name="mappings"/>
</assembly>
```

`oscal_mapping_metaschema_RESOLVED.xml`, `mapping-collection`. One attribute
that is present everywhere else and absent there is the whole reason a model is
unread.

## Decision

Resolve that shape, and only that shape.

A two-branch `anyOf` where one branch is `{"$ref": X}` and the other is an
array whose `items` is the identical `{"$ref": X}` is read as what it says:
one X, or an array of X. `anyOf` requires the instance to satisfy at least one
branch; the branches name the same definition and one of them requires an
array, so a JSON array can satisfy only the array branch and a JSON object can
satisfy only the other. The schema decides which applies, and the walk chooses
nothing.

The guard is that the two `$ref`s must be identical. Two different targets are
a real choice between alternatives, the resolver declines it, and the subtree
is still reported `SUBTREE_NOT_READ` rather than guessed at. That is the line
the issue drew: a walker that half-resolves alternatives and reports findings
against a shape it guessed at would be worse than an honest decline.

A value that is neither an array nor an object reaches X itself and is reported
against the type X declares, which is `"type": "object"`, a type the schema
states. It is deliberately not reported against a description of the choice:
this tool's findings quote the schema, and `"type": "object or array"` is not
a thing the schema says.

## Consequences

- The eighth model is read. Required properties, properties the schema forbids,
  JSON types, `minItems`, UUID uniqueness across the document, datatypes, and
  bare `#` fragment references now all reach inside a mapping.
- `tests/test_break_the_gate.py` gains a proven-clean synthetic mapping
  collection and seven corruptions inside `/mapping-collection/mappings`, each
  of which produced 0 ERROR before this change. The model has a gate.
- On the seven published mapping collections already in the corpus, all seven
  `SUBTREE_NOT_READ` findings are gone and 31 ERROR findings appear where there
  were none. Four shapes, each verified by hand against the vendored schema:
  `id_ref` written where `mapping-item` declares `id-ref` and forbids anything
  else, `confidence-score/percentage` written as a string where the schema
  declares `DecimalDatatype`, `with-ids` present and empty where the schema
  declares `minItems: 1`, and `source-resource`/`target-resource` fragments
  naming the value of a resource's `props/id` rather than the resource's own
  `uuid`. Three of the seven documents declare a pre-1.2 release, so which of
  their findings turn on the version difference is
  [issue #8](https://github.com/ChelseaKR/oscal-validate/issues/8)'s open
  question, not this ADR's.
- The published limitation is now historical, and every place that stated it
  says so with a date and a pointer here. A stale limitation is as misleading
  as a stale number.
- `SUBTREE_NOT_READ` remains reachable and is not dead code: it still reports
  an array with no declared item shape, object alternatives that disagree about
  what a property means, and object alternatives where the value is not an
  object.
- `tests/test_schema_and_walk.py` pins both counts, one and three, against the
  vendored file. A later OSCAL release that writes the shape somewhere else, or
  that adds a declined shape a document can land on, fails that test rather
  than quietly widening what this ADR claims.
