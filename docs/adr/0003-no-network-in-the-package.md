# 3. The installed package opens no network connection, in any command

## Status

Accepted

## Context

An OSCAL document names other documents by URL. It is tempting for a validator
to fetch them: the references would resolve, the reports would be shorter, and
the UNVERIFIABLE severity would mostly disappear.

It would also mean that a clean run depends on what a URL served that morning,
that running the tool tells a third party which package you are about to
submit, and that the tool would be fetching URLs written inside untrusted input.

The sibling project in this portfolio put fetching behind a separate subcommand
with a documented posture. Here, the documents that would be fetched are
supplied locally in every workflow this tool is for: a publisher checking a
package already has the baseline they built it against.

## Decision

- The installed package has no network capability in any command. Nothing under
  `src/` imports `urllib.request`, `http.client`, `socket`, `requests`, or
  `httpx`, and a test enforces that by reading the source.
- Imported documents are supplied with `--resolve`, from local files or a
  directory. Unresolved references are UNVERIFIABLE, with the missing file
  named.
- The one thing in this repository that opens a socket is `tools/fetch.py`, a
  development harness for collecting the documents behind `docs/findings/`. It
  is not installed, is not reachable from the CLI, and its posture (robots.txt
  first and obeyed with no override flag, identifying User-Agent, byte cap,
  timeout, per-host rate limit, five redirects with robots re-checked at each
  hop) is tested against a server on localhost.

## Consequences

- Validation is reproducible and offline. `tests/test_offline_guarantee.py`
  removes `socket` and runs it anyway.
- Reports are longer, because most reference questions are unanswerable without
  the imported documents, and the tool says so rather than fetching.
- A user who wants full resolution has to gather the documents. That is a real
  cost, and it is the cost of a gate that cannot flake and cannot leak.
