# 0. Record architecture decisions

## Status

Accepted

## Context

oscal-validate makes a small number of consequential, hard-to-reverse
decisions: what the tool refuses to check without a citable source, how
severities are defined (in particular that UNVERIFIABLE never gates the exit
code and is never collapsed into a pass), why the schema and constraint
snapshots are vendored, and where the boundary sits between checking a document
and judging a system. The reasoning behind a structural choice must not live
only in a commit message, or a later change will either re-litigate a settled
question or unknowingly reverse a decision made for a reason nobody re-reads.

## Decision

We will record architecture decisions in Architecture Decision Records
(ADRs) using the format described by Michael Nygard.

- Each ADR is a short Markdown file in `docs/adr/`, numbered sequentially
  and named `NNNN-title-in-kebab-case.md`.
- Each ADR has the sections **Title**, **Status**, **Context**, **Decision**,
  and **Consequences**.
- **Status** is one of *Proposed*, *Accepted*, *Deprecated*, or *Superseded*.
  A superseded ADR is not deleted; it is marked superseded and points to the
  ADR that replaces it, and the replacement points back.
- ADRs are immutable once accepted, except to change their status. A new
  decision is a new ADR, not an edit to an old one.

## Consequences

- The reasoning behind structural decisions is preserved and versioned
  alongside the code it explains.
- Writing an ADR is a small, deliberate friction on consequential change;
  that is intended, since it makes reversing a load-bearing decision a
  visible act rather than an accident.
- ADRs capture decisions, not the full design: the README's methodology
  sections remain the narrative; ADRs record why the load-bearing choices
  were made.
