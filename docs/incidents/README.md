# Incidents

Zero to date. That is a count, not an exemption, and this directory exists so
the first one has somewhere to go that survives the repository being archived.

## When something goes wrong

A postmortem is a file here, named `YYYY-MM-DD-<slug>.md`, committed. Not a
comment on an issue: issues get transferred, deleted, or lost, and a committed
file stays with the code that caused the problem.

An incident in this repository would be one of two shapes, because there is no
service to take down:

- **A wrong answer with consequences.** This tool's harm surface is false
  assurance: a document reported clean that was not, or a correct document
  reported as failing. The second kind has already happened once, was caught by
  a survey run rather than by a user, and is written up in
  [`../findings/2026-08-15-imports-supplied-survey.md`](../findings/2026-08-15-imports-supplied-survey.md)
  under Finding 4. Had it reached anyone downstream it would have been an
  incident and would live here.
- **A supply-chain or disclosure event.** A secret committed, a dependency
  compromised, a vendored file replaced with something that is not what NIST
  published. [`../../SECURITY.md`](../../SECURITY.md) is the reporting channel.

## What a postmortem says

What happened, when it started and when it stopped, who or what was affected,
how it was found, the root cause, and the action items with owners. Blameless:
the subject is the system that let it happen.

Two things specific to this tool belong in any postmortem about a wrong answer:
which severity the tool gave and which it should have given, and whether the
existing gates could in principle have caught it. `tests/test_break_the_gate.py`
is the place a new corruption case goes, and adding one is not optional
follow-up.

## Open gap

The portfolio incident-response standard also asks for `incident` and `sev1`
through `sev4` labels on the repository. Those are a GitHub settings change and
cannot be made from inside the repository; they have not been created. This is
recorded in [`../ROADMAP.md`](../ROADMAP.md) rather than claimed as done.
