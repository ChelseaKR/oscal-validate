# Responsible-Tech Audits: oscal-validate

Project-specific findings under the portfolio Responsible-Tech Framework. This
artifact is reviewed on release; generic thresholds remain in the portfolio
standards. Last reviewed: 2026-08-14 (initial).

## Applicability

- **A Ethics:** applies. The harm surface is false assurance about a security
  authorization.
- **B Bias:** minimal surface; the tool applies published structural rules
  uniformly to every document and does not rank, score, or profile. It grades
  documents, never the organizations that publish them.
- **C Privacy / DPIA:** applies in a narrow form. The tool processes only the
  local files it is pointed at, entirely in process, with no network calls, no
  telemetry, and no persistence beyond its printed report.
- **D Transparency:** applies and is the design center: every finding carries
  the rule citation, source URL, and retrieval date it enforces, and every
  unevaluated rule is listed.
- **E Accessibility:** N/A today; no graphical or web surface. Output is plain
  text (screen-reader-friendly terminal output) plus `--format json`.
- **F Security:** applies; see `SECURITY.md`. Input is untrusted JSON.
- **G Effect on third parties:** applies to the survey harness only, which
  fetches other people's servers.
- **AI Evaluation:** N/A; no LLM or model call exists anywhere in the tool.
  AI-assisted authoring of the code is disclosed in the README.

## A. Ethics: false assurance is the whole harm

**What could go wrong?** The documents this tool reads support decisions about
whether a system is allowed to operate. The dangerous failure is not a spurious
error, which a human investigates, but a clean report that a reader takes as
evidence of compliance. Three specific ways that could happen:

(a) A reader takes "no ERROR findings" as "this package conforms to OSCAL" when
the tool evaluates 78 of NIST's 340 published constraints. (b) A reader takes
structural conformance as evidence that a control is implemented. (c) A
reference that could not be checked, because the imported document was not
supplied, is read as one that was checked and passed.

**Controls.** The README opens with the structural-conformance boundary stated
before anything else, and the Limits section enumerates every check the tool
does not perform. The severity contract makes UNVERIFIABLE a first-class
outcome that is never rendered as a pass (ADR-0002), and every run emits
UNVERIFIABLE findings naming what was not checked and how much of it there was,
including runs with no other findings. `docs/CONSTRAINT-COVERAGE.md` lists all
340 published constraints with whether each is evaluated, is generated from the
vendored files, and is guarded by a test so it cannot drift.
`tests/test_break_the_gate.py` proves each claimed check actually catches its
target. `SECURITY.md` classifies both a false clean report and an UNVERIFIABLE
collapsed into a pass as security bugs.

**Review gate.** Any change to severity semantics, or to what a check claims,
requires an ADR and a README scope update in the same PR.

### A2. Ethics: findings are about documents, never about people or products

**What could go wrong?** A tool that reports defects in other organizations'
published files can slide into a scoreboard, or into a claim about the security
of the systems those files describe.

**Controls.** Findings are stated as conformance of a published document to the
published specification, on a stated date, and nothing more. The survey records
metadata and finding codes only, never a value read from anyone's document.
This project does not open issues or pull requests on NIST, FedRAMP, or any
vendor's repositories, and does not characterize anyone's software; that rule is
written into `CONTRIBUTING.md`. Where a finding could be read as a claim about a
tool that produced a document, the write-up describes the document instead.

**Accepted cost.** Some findings are less satisfying to read because they stop
short of naming a cause. That is the correct place to stop.

## B. Bias and fairness

The rules come verbatim from NIST's published schema, constraint layer, and
documentation; the tool adds no discretionary judgment per document. Constraint
severity is NIST's declared level rather than one this tool assigns. Where the
tool makes an interpretive choice, there is exactly one, it is documented in the
README's Limits section and in the code, and it is the reading under which
NIST's own published catalogs are not spuriously invalid.

## C. Privacy

No collection, no transmission, no retention. The DPIA-style answer is short
because the data flow is short: files in, findings out, process ends. This
matters more than usual here, because system security plans and assessment
results describe live systems' boundaries, components, and unremediated
weaknesses. Nothing leaves the machine the tool runs on, and there is no code
path that could send it anywhere. Findings quote document values back to the
operator, which is necessary for a usable report; operators handling sensitive
packages should treat the report with the same care as the package.
`SECURITY.md` asks reporters never to attach a real SSP, SAR, or POA&M.

## D. Transparency

The methodology, severity definitions, scope limits, and the one interpretive
choice are documented in the README. The vendored sources and their hashes are
in `src/oscal_validate/vendor/SOURCES.md`. A finding without a citation cannot
be constructed in the code path: the `Finding` model requires a `Rule`.

## F. Security

See `SECURITY.md` for the threat cases and the commitments. The validator runs
offline by design, which removes the largest attack classes, and that is
enforced by a test that removes `socket` and by a test that reads the package
source for network imports. The residual surface is the JSON parser, the
vendored XML parse (hash-checked input, never user-supplied), and the supply
chain of the dev toolchain. Documents nested past 200 levels are refused rather
than read partially.

## G. Effect on the sites the survey harness fetches

**What could go wrong?** A tool that fetches other people's repositories can
cost them money and attention: ignoring robots.txt, hammering a host, hiding
behind a browser's User-Agent, or wandering off the documents it was pointed at.

**Controls.** robots.txt is fetched before anything else and obeyed, with a
Disallow as a hard stop and no flag to override it; an unreachable robots.txt is
treated as a complete disallow per RFC 9309 2.3.1.4 rather than as permission. A
blocked host is recorded in the evidence and skipped, never circumvented. The
User-Agent carries the product token and a link to this repository. One
invocation fetches robots.txt plus the documents on its target list, with a
two-second minimum interval per host that a declared `Crawl-delay` can lengthen.
Redirects are capped at five with robots re-checked at every hop. Every one of
these is tested against a server on localhost in `tests/test_survey_fetch.py`,
including the case where the document is never requested because robots.txt said
not to. Fetched bytes are cached so a re-run needs no network at all.

**Residual risk.** The operator chooses the target list, and a tool cannot know
whether they had a reason to. What it can do is behave the same way whoever is
driving it, and leave a log entry that says who it was.
