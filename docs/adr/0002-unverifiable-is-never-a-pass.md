# 2. UNVERIFIABLE is a first-class outcome and is never collapsed into a pass

## Status

Accepted

## Context

This tool runs against documents that support security authorization decisions.
The dangerous failure is not a false alarm, which a human investigates; it is a
clean report that a reader takes as assurance. Three situations produce that
risk:

1. A reference points into a document the tool was not given. OSCAL identifiers
   are explicitly cross-instance scoped, so the target may exist and the tool
   cannot know.
2. NIST publishes 340 constraints and this tool evaluates 78. The other 262 are
   not violations and are not passes.
3. Two OSCAL datatype patterns use ECMA-262 Unicode property escapes that
   Python's `re` cannot compile.

In every one of these the tool has *not looked*, and the difference between
"looked and found nothing" and "did not look" is the entire value of the
report.

## Decision

- A fourth severity, UNVERIFIABLE, sits beside ERROR, WARNING, and INFO. It
  never gates the exit code and is never rendered as a pass or a fail.
- Every one of the three situations above emits UNVERIFIABLE findings naming
  what was not checked and how much of it there was, on every run, including
  runs with no other findings.
- A document's *effective data model*, as NIST defines it, decides between
  ERROR and UNVERIFIABLE for an unresolved reference: complete means the
  reference resolves to nothing and is wrong; incomplete means the answer is
  unknown, and the report names the missing file.
- Collapsing UNVERIFIABLE into clean is classified in `SECURITY.md` as the same
  class of bug as a false clean report.

## Consequences

- Every report, including a clean one, carries several UNVERIFIABLE findings.
  This is noisier than a tool that stays silent about its own limits, and it is
  the point.
- The exit code stays usable in CI: only ERROR gates it.
- A user who wants a definite answer about a reference has an action available
  (`--resolve`), and the report tells them exactly which file to supply.
