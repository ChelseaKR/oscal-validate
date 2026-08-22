# 5. Model-backed commands at the edges, a validator that stays the only source of findings

Date: 2026-08-21

## Status

Accepted (owner-directed change of direction). Amends ADR-0003: its
guarantee now covers the validation commands rather than "any command".

## Context

Until this decision the README opened with three promises: "No network
calls, in any command. No model calls, ever. Same input, same output, byte
for byte." ADR-0003 made the first mechanically checkable, and
`tests/test_offline_guarantee.py` read every file under `src/` to prove it.
`docs/RESPONSIBLE-TECH-AUDITS.md` and the standards table recorded AI
Evaluation as not applicable because no model call existed.

The owner has directed that the tool add substantial, real AI features. The
reason is the people who author these documents: a finding such as
`CONSTRAINT_NOT_UNIQUE` at `/catalog/groups/16/controls/23/id`, cited to a
Metaschema constraint by identifier, is correct and is not easy to act on.
Explaining what the rule means, proposing a concrete edit, ordering a long
report by what to fix first, and answering "why does NIST have this
constraint" are all things a language model can do well, and all things an
ungrounded model does badly: it will paraphrase a definition it has not
read, propose an edit that breaks something else, describe a finding the
validator never produced, or drift from "this reference is dangling" into
"this control is not implemented". The last of those is the boundary the
README was written around. A structural validator that starts offering
opinions about whether a system is secure is a worse tool than one that
offers nothing.

## Decision

Four opt-in subcommands call a model: `explain`, `repair --draft`,
`walkthrough`, and `ask`. They live in `oscal_validate.ai`, a subpackage
nothing in the validator imports, and the SDK they use is an optional extra
(`pip install 'oscal-validate[ai]'`) imported lazily inside the command.
The bare command, `oscal-validate <file>`, is unchanged: it imports none of
this, opens no socket, and produces the bytes it produced before. The rules
that bind the four commands:

1. **The validator is the only thing that produces a finding.** Every
   model-backed command starts by running the deterministic validator and
   works from its findings list. A model never classifies a document, never
   assigns a severity, and never adds or removes a finding. The walkthrough
   is checked after generation: a finding label it mentions that the
   validator did not produce is struck and counted, and a finding it omits
   is appended under its own heading, so nothing is invented and nothing is
   suppressed.

2. **NIST's published text is the only evidence.** `oscal_validate/ai/corpus/`
   holds committed copies of the NIST pages the rules already cite, with
   URL, retrieval date, and SHA-256 for each, beside the vendored schema and
   metaschema that were already there. A model explains a rule by quoting
   that text; every quote is checked verbatim against the corpus before
   anything is displayed. A quote that does not resolve is withheld and the
   count of withheld quotes is printed. A NIST definition is never
   paraphrased without a verified quote beside it.

3. **A repair is a draft, verified by re-validation, never applied.** A
   proposed fix is a JSON Patch against an in-memory copy of the document.
   Before it is shown, the copy is re-validated by the same deterministic
   validator, and the report states what that run found: which finding the
   patch resolves, which it leaves untouched, and which findings it
   introduces, if any. The original file is never written. `--out` writes
   the patched copy to a different path only.

4. **The boundary is enforced in code, not only in the prompt.** The model
   is instructed to refuse any question of whether a control is implemented,
   whether a system is secure, or whether a package would be authorized,
   and to redirect to structural conformance and qualified assessment. A
   separate, deterministic guard then scans every rendered output for
   implementation, security, or authorization judgments, withholds any
   sentence that carries one, and counts it. The adversarial suite in
   `evals/` measures both layers separately and reports both numbers.

5. **Honest refusals.** A finding whose rule has no corpus source, a
   document the validator cannot parse, and a document declaring an OSCAL
   version the vendored schema does not describe (issue #8) are each
   reported as such by the model-backed commands, which then stop. No
   command fills a gap the validator left open.

6. **Provenance on every measurement.** The evaluation harness and its cases
   are committed. A results file is accepted only when it names the
   provider, model, prompt version, tool commit, and date it was produced
   under, and a test rejects one that does not. Numbers appear in the
   documentation only from a recorded live run; otherwise the suite is
   labeled not run.

Provider and model: the public `anthropic` SDK, default `claude-sonnet-5`,
configurable by environment. Amazon Bedrock is reachable through the same
SDK. Credentials come from the environment only and are never written to
any file this tool creates.

## Consequences

- The README's opening promise is rewritten to say what is now true: the
  validation commands make no network and no model calls, and four named
  commands do, opt-in, with the validator deciding everything that is a
  finding. `SECURITY.md`, `CONTRIBUTING.md`, `docs/RESPONSIBLE-TECH-AUDITS.md`,
  `docs/ROADMAP.md`, and the standards table change in the same series.
  "AI Evaluation" becomes a standard that applies, with the evaluation
  harness as its evidence.
- `tests/test_offline_guarantee.py` is rescoped rather than weakened: the
  source scan covers everything outside `oscal_validate/ai/`, a new test
  asserts that nothing outside that package imports it and that it imports
  the SDK only inside functions, and a subprocess test proves that running
  the default command loads none of it.
- `tests/golden/` pins the default path's exact bytes over the fixtures and
  over eight published NIST documents, captured from the last commit before
  this change. Any drift in the default output fails the build.
- The tool gains an optional dependency and, for users who opt in, a
  network call to a model provider carrying the findings, the corpus
  passages, and excerpts of the document being validated. A system security
  plan can contain sensitive detail. That cost is stated in the README next
  to the commands, and the commands are never run by the GitHub Action.
- The boundary guard will sometimes withhold a sentence that was not a
  judgment. That is the intended direction of error, and the withheld count
  is printed so the reader can see it happened.
