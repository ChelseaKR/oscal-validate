# 8. Version skew is flagged, not resolved

Date: 2026-09-06

## Status

Accepted

## Context

Everything is validated against the vendored OSCAL 1.2.3 schema and constraint
layer. `OSCAL_VERSION_DIFFERS` fires at WARNING on every document declaring
anything else, which was every document in the first sample and every document
in the widened one.

That was sufficient while every ERROR in the corpus was version-independent. A
duplicate UUID, a dangling fragment and a missing timezone are wrong in every
OSCAL release, so nothing turned on which release the document named.

The widened corpus produced the first ERRORs that do turn on it
([issue #8](https://github.com/ChelseaKR/oscal-validate/issues/8)):

| Document | declares | finding |
|---|---|---|
| `mapping-collection.json` (OSCAL Compass) | 1.1.2 | `TYPE_MISMATCH` on `provenance/method`, `NO_SCHEMA_ALTERNATIVE` on `provenance/confidence-score` |
| `splunk-demo.json` (GovReady) | 1.0.0-rc1 | `TYPE_MISMATCH`: `components` is an object where 1.2.3 declares an array |

Two neighbouring findings survived the same check and are ordinary true
positives: BSI's `qa-note`/`qa-reviewed` under `provenance`, verified against
NIST's published v1.1.2 schema, and three mapping collections declaring
releases in which `mapping-collection` does not exist at all.

**The problem was not the findings. It was that the check was a manual step in
a write-up.** It cost two schema fetches and a paragraph of prose per finding,
it is reproducible by nothing in this repository, nothing stops the next run
from reporting a version-skew ERROR with no such check behind it, and a reader
of the report itself sees none of it. A reader taking "9 of 43 documents
carried at least one ERROR" at face value was being told something slightly
stronger than what was measured.

## Decision

**Report the skew as its own finding. Do not attempt to resolve it.**

A new INFO code, `VERSION_SKEW_SUSPECTED`, is emitted once per declared
`oscal-version` that differs from the vendored release, when and only when the
report also carries at least one ERROR. It states how many ERRORs there are and
under which codes, that no schema for the declared release is vendored here,
and therefore that whether each of them is also an error under that release was
not determined by this run.

It is a record that a question was not settled. It is never a verdict that an
ERROR is wrong.

Issue #8 set out four options. The other three were rejected:

1. **Leave it.** Defensible — every rule citation already names the vendored
   schema and its version, and the finding is literally true as cited. Rejected
   because "literally true as cited" is exactly the condition under which a
   reader draws a stronger conclusion than the evidence supports, and because
   the manual check would stay manual.
2. **Downgrade version-skew findings to WARNING.** Rejected: it requires
   knowing which findings are version-sensitive, which is not knowable without
   the other schema. It would move a severity on a guess.
3. **Vendor more than one schema and validate against the declared version.**
   Correct, and out of scope for this decision. `SOURCES.md`, the hash pinning,
   `tests/test_vendor_integrity.py`, the constraint-coverage table and the
   README's account of itself all assume exactly one vendored schema. Changing
   that changes what this project claims to be, and belongs to its owner rather
   than to the issue that noticed the gap. **This ADR deliberately leaves it
   open**, and the new finding is the hook a later decision would hang on: a
   document already says, in its own report, which ERRORs a second schema would
   settle.

## Consequences

**The default report changes for one class of document.** A document that both
declares a non-vendored release and carries an ERROR gains one INFO finding.
Nothing else moves: no severity changes, no ERROR is added or removed, and the
exit code is unchanged, since only ERROR findings make the CLI exit nonzero. Of
the twelve cases pinned in `tests/golden/`, two are in that class and each
gains exactly one line per format. That is the eighth recorded re-capture of
the byte-identity goldens and the reason is written into
`tests/test_default_path_byte_identity.py` beside the other seven.

**INFO rather than UNVERIFIABLE.** UNVERIFIABLE means the validator did not
decide the question it was asked, and is never counted as a pass or a fail.
Here the question it was asked — does this document conform to OSCAL 1.2.3? —
*was* decided, and the answer is the ERROR. What is undecided is a second and
different question: is it also an error under the release the document names?
Scoring the first as unsettled because the second is would understate a real
result, and would move findings out of the ERROR count that belong in it.

**One flag per document, not one per ERROR.** Placing it beside each ERROR
would read better on a short report and would have added 35 INFO findings to
the longest one in the corpus, so the flag sits at the `oscal-version` scalar,
where the deterministic ordering puts it immediately after
`OSCAL_VERSION_DIFFERS`, and names the affected codes with their counts
instead.

**It is not emitted where there is nothing to qualify.** A clean document that
declares an older release gets the WARNING and no INFO: there is no ERROR whose
version-sensitivity is in question. A document with no `oscal-version` at all
gets neither, because there is no declared release to be skewed from; the
schema requires the property, so its absence is already an ERROR on its own
terms. `tests/test_finding_code_census.py` asserts each of those three
non-emissions directly, so the witness for the code cannot pass for the wrong
half of its condition.

**One sentence deliberately still cites the issue rather than this ADR.** The
"Declared version" tier in `src/oscal_validate/fixorder.py` says "(issue #8)",
and that tier's prose is carried into the walkthrough prompt, which is hashed to key
`tests/cassettes/walkthrough-nist-ssp.json`. Rewording it invalidates a
recording that only a billed, networked re-record can replace, which is not a
price worth paying for a citation. The new code is added to that tier's code
list, which does not touch the prompt: a code with no findings in the run
produces no group.

**The write-up's worked examples stay in step.** Finding 2 and Finding 4 of the
2026-08-19 survey are the documents this ADR is about; the flag now appears in
any re-run over them, which is where the manual paragraph used to go.
