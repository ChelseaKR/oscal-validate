# Security policy

oscal-validate is a deterministic, offline validator: it reads local JSON
files, checks them against vendored schema and constraint snapshots, and prints
findings. It makes no network calls in any command and has zero runtime
dependencies. Security here is mostly integrity: the tool must not misreport
what a document contains, and crafted input must not escape the documented
failure modes.

The one component in this repository that opens a socket is `tools/fetch.py`,
the development harness behind `docs/findings/`. It is not part of the installed
package and is not reachable from the CLI. It fetches `robots.txt` first and
obeys it, over http or https only, with an identifying User-Agent, a byte cap, a
timeout, a per-host rate limit, and at most five redirects with robots re-checked
at every hop.

## Supported versions

This is a pre-1.0 tool; there is no tagged release yet. Security fixes land on
`main` and, once one exists, the latest tagged release.

| Version | Supported |
| ------- | --------- |
| `main` / latest tag | yes |
| older tags | no |

## Reporting a vulnerability

Preferred: GitHub private vulnerability reporting (this repository's *Security*
tab, "Report a vulnerability"). Alternatively, email ckellyreif@gmail.com with
`oscal-validate security` in the subject. Expect an acknowledgement within 72
hours; this is a volunteer project, so please do not disclose publicly until a
fix is available.

Reproduce issues with synthetic documents like the fixtures under
`tests/fixtures/`. **Never attach a real system security plan, assessment
result, POA&M, or any other document describing a live system's controls,
vulnerabilities, or boundaries.** Reduce it to the smallest synthetic case that
reproduces the behavior.

## What we consider a vulnerability

In addition to the usual (code execution from input data, secret exposure,
supply-chain compromise), the following are first-class security bugs here:

- Crafted JSON input that crashes outside the documented exit-code contract
  (0 = no ERROR findings, 1 = ERROR findings, 2 = unreadable input), hangs, or
  consumes unbounded resources.
- **Any path by which the tool reports a clean pass on a document that violates
  a rule it claims to check.** A false clean report is an integrity bug, not a
  cosmetic one: this tool exists to be run before a package is handed to
  someone.
- **Any path by which something the tool did not check is rendered as a pass.**
  UNVERIFIABLE must never be collapsed into clean. The distinction is the whole
  contract, and losing it is the same class of bug as a false clean report.
- Any way to alter the vendored schema or constraint snapshots that
  `tests/test_vendor_integrity.py` and the recorded SHA-256 hashes in
  `src/oscal_validate/vendor/SOURCES.md` would not catch.
- Any path by which the installed package opens a network connection, resolves
  an external schema, or reads a file it was not given on the command line.
- Any path by which `tools/fetch.py` fetches something a `robots.txt` disallows,
  or reaches a scheme other than http and https. There is deliberately no flag
  to disable the robots check; a way to bypass it is a vulnerability, not a
  feature request.

## What is out of scope

A finding this tool did not report because it does not implement that check is
not a vulnerability; it is the documented scope, and the README's "Limits"
section and `docs/CONSTRAINT-COVERAGE.md` enumerate it. Reports that the tool
failed to detect an unimplemented control, an insecure configuration, or an
inadequate assessment are out of scope by design: this tool reads documents, not
systems.

## Our commitments

- Dependencies are locked (`uv.lock`) and audited with pip-audit in
  `make verify` and CI, plus Dependabot updates; Semgrep and a full-history
  TruffleHog sweep run in CI; every GitHub Action is pinned to a full commit
  SHA. `make verify` is the same gate locally and in CI.
- Integrity regressions (false clean reports, or UNVERIFIABLE rendered as a
  pass) are fixed with the highest priority.
- We credit reporters who want credit, and respect those who want anonymity.
