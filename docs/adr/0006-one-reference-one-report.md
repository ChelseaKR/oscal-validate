# 6. One reference, one report, and the unsettled one is the one published

Date: 2026-08-27

## Status

Accepted

## Context

Two checks reach the same identifier reference. NIST's constraint layer
evaluates `index-has-key` constraints, several of which target a link and take
their key from `@href` with NIST's own `pattern="#(.*)"`. Check 4 enforces the
prose rule in NIST's URI Usage page over every bare `#` fragment the schema
calls an `href`. Both are correct, both are cited, and on a bare fragment they
land on the same value.

`validator.py::_deduplicate` was written to merge them. It never did. It keyed
on `(location, value)` as each check spelled them, and the two spell both
differently and correctly: the constraint layer reports against the node its
target expression selected, `.../links/0`, with the `#` already stripped by
NIST's pattern, and the prose check reports against the scalar it read,
`.../links/0/href`, with the value as written. Two keys, no merge, and
`_prefer` was never once called with anything to prefer, which is why
`validator.py` carried an uncovered line for as long as the merge existed.

What reached the reader was one defect reported twice under two citations at
two pointers, and in one case reported twice with opposite verdicts. A
`provided-by` link whose fragment names nothing produced both
`REFERENCE_UNVERIFIABLE` ("the index was never built, so this key could not be
looked up in it") and `REFERENCE_UNRESOLVED` at ERROR ("the effective data
model is complete and this reference resolves to nothing"), about one href, in
one report.

Normalizing the key alone makes it worse rather than better. `_prefer` decided
between two findings by looking for the string `NIST OSCAL constraint` in the
citation, as a proxy for "this came from the constraint layer". The proxy holds
only when that check settled the question: an unsettled constraint finding
cites the prose rule about cross-instance scope, so the proxy misses it and the
prose ERROR wins. The UNVERIFIABLE disappears, the unbuilt index stops being
named, and the gate test
`test_a_lookup_into_an_index_that_was_never_built_is_never_an_error` in
`tests/test_break_the_gate.py` fails on the assertion that exists for exactly
this: "the unbuilt index must be named, not silently passed."

## Decision

**Settledness decides first, and it outranks both severity and citation.**
Where two reports about one reference disagree about whether the question was
settled, the unsettled one is published.

A settled finding says the reference resolves to nothing: a claim about the
reader's document. An unsettled one says the documents in hand cannot answer:
a claim about this tool's reach. A check that has just reported it could not
perform a lookup does not become able to perform it because another check,
looking somewhere else, came back empty.

The case is not hypothetical and it is not symmetric. A constraint finding can
be unsettled while a prose finding is settled in exactly one way: an
`index-has-key` reading an index that was never built. OSCAL 1.2.3 publishes
one, `oscal-by-component-uuid-index` on `link[@rel='provided-by']`, and NIST
declares the index it reads over

    control-implementation/implemented-requirement//by-component
    | doc(system-implementation/leveraged-authorization/link[@rel='system-security-plan']/@href)
      /system-security-plan/control-implementation/implemented-requirement//by-component

A leveraged authorization's SSP arrives through a link, not through an import.
`--resolve` completeness is measured over imports, so "every import was
supplied" is not a stronger answer about a `provided-by` href; it answers a
smaller question, and the target may sit in a document this tool was never
given and could not have opened. Publishing the ERROR would report a defect in
someone's file on the strength of a lookup the same report says was not made,
which is what ADR-0002 forbids, and `docs/CONSTRAINT-COVERAGE.md` already tells
readers it does not happen: "References checked against them are reported
UNVERIFIABLE, naming the index, and are never reported as failures of the
document."

**Severity ordering was rejected.** It reaches the right answer here for the
wrong reason and the wrong answer elsewhere. NIST's published `level` is
carried into the severity, so a settled constraint failure can be a WARNING,
and an order that ranked by severity would drop it for a prose ERROR and
silently raise NIST's own published level.

**Which check reported it is stated, not inferred from a citation string.**
Where two reports agree on settledness, `REFERENCE_PRECEDENCE` names the order:
the constraint layer, then the prose check. The constraint layer's report names
NIST's constraint, the index it read, and the level NIST published; the prose
check's names a documentation page. Ties keep the report already held. The
citation-sniffing proxy is gone, so no future change to a rule's wording can
silently invert which report survives.

**An unsettled report cites the reason it is unsettled.** The two reasons are
different rules and a reader acts on them differently. An index that was never
built is this tool's own limit and no supplied document changes it; it now
cites `INDEX_NEVER_BUILT`, tool policy in the same form as `NOT_WALKED_POLICY`
and `UNCOMPILABLE_PATTERN`. A document named by an import that was not supplied
is what NIST's cross-instance scope paragraph is about, and `--resolve` settles
it; it still cites `CROSS_INSTANCE_SCOPE`. Both are chosen from the same fact
the message is chosen from, so the citation and the message cannot come apart.

A constraint the tool did not evaluate is never the authority for the finding
that it could not evaluate it. Citing `constraint_rule(...)` on an unsettled
finding would make `_prefer`'s old proxy work, and it would put a formal NIST
constraint id behind a check this tool is saying it did not perform.

## Consequences

- One href produces one report. Where the two checks agree, the reader sees
  the constraint citation, which is the more specific of the two.
- A `provided-by` fragment that names nothing, in a document whose imports were
  all supplied, is UNVERIFIABLE and not an ERROR, so it no longer gates the
  exit code. That is the ADR-0002 trade: the run is not clean, it carries an
  UNVERIFIABLE finding naming the index, and the tool does not claim a defect
  it cannot demonstrate. `oscal-by-component-uuid-index` is the only constraint
  in that position in OSCAL 1.2.3, and the generated coverage table lists it.
- The dropped report's own sentence is dropped with it. The reader is not told
  "and no identifier anywhere in the supplied documents matches this either".
  Merging the two messages would publish a sentence no check wrote, and
  publishing both is the defect this ADR exists to fix; the surviving report
  says what was and was not done. If that proves too little, the answer is a
  richer finding model, not a second line that contradicts the first.
- `_prefer` is now exercised. The merge path was dead code, and
  `src/oscal_validate/validator.py` goes to 100% line and branch coverage.
