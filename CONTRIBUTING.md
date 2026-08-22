# Contributing to oscal-validate

Thank you for considering a contribution. The premise of this tool is that
every finding cites a published rule, that the same input always produces the
same output byte for byte, and that anything it did not check is reported
rather than passed. Contributing here carries three obligations beyond the
usual: never encode a rule from memory, never break determinism, and never let
an unchecked thing render as clean.

If you have not yet, read [`README.md`](README.md) for what the tool is and
why, and [`SECURITY.md`](SECURITY.md) for how to report a vulnerability.

## Getting set up

oscal-validate targets Python 3.12 (see `.python-version`) and uses
[`uv`](https://docs.astral.sh/uv/) for a reproducible, locked environment:

```sh
uv sync --locked
uvx pre-commit install   # optional but recommended: ruff/mypy/gitleaks on commit
```

## The merge gate

A change merges when the full gate is green. Reproduce it locally with:

```sh
make verify
```

`make verify` runs the exact same targets `ci.yml` invokes, on the same locked
toolchain, so green locally means green in CI:

| Gate | Command | What it checks |
| --- | --- | --- |
| Lint | `make lint` | `ruff check`: correctness, import hygiene, modern idioms, cyclomatic complexity (<= 10) |
| Format | `make format` | `ruff format --check` |
| Types | `make typecheck` | `mypy --strict` over `src`, `tests`, and `tools` |
| Tests + coverage | `make test` | pytest with branch coverage >= 90% |
| Dependency audit | `make audit` | pip-audit against the locked environment |

Five invariants are called out separately because they protect the tool's core
promises:

- **Cited rules only.** Every check traces to a vendored schema declaration, a
  vendored metaschema constraint, or a prose rule quoted in
  `src/oscal_validate/rules.py` with its source URL and retrieval date.
  Updating a rule means updating the vendored snapshot and its recorded SHA-256
  in `src/oscal_validate/vendor/SOURCES.md`, not editing a constant to match
  memory.
- **Nothing unchecked is ever clean.** A construct the tool cannot evaluate
  gets an UNVERIFIABLE finding naming it. Silence is not an option, and neither
  is a heuristic that guesses at the answer.
- **Determinism.** `tests/test_determinism.py` asserts byte-identical output
  across runs and across interpreter processes. No timestamps, no sampling, no
  network.
- **The validator stays offline.** Nothing under `src/` outside
  `oscal_validate/ai/` may import `urllib.request`, `http.client`, `socket`,
  `requests`, `httpx`, or `anthropic`; nothing outside `ai/` may import `ai/`;
  and `ai/` may import the SDK only inside a function.
  `tests/test_offline_guarantee.py` enforces all three by reading the source,
  and `tests/test_default_path_byte_identity.py` pins the default command's
  exact bytes against goldens captured before the AI layer existed. A change
  that makes the validator itself touch the network is a change to what this
  tool claims to be, and needs an ADR before it needs a review.
- **The coverage table is generated.** `docs/CONSTRAINT-COVERAGE.md` comes from
  `make coverage-doc`; `tests/test_constraint_coverage.py` fails if the
  committed copy is stale. Do not hand-edit it.

New checks should come with a break-the-gate case in
`tests/test_break_the_gate.py`: corrupt a proven-clean document in exactly the
way the check exists to catch, and assert it is caught.

Changes to `tools/fetch.py` deserve extra care: it is the only module in the
project that opens a socket, its posture is documented in its own docstring and
in the README, and `tests/test_survey_fetch.py` proves each promise against a
server on localhost. Adding a way around the robots.txt check will not be
merged.

## Do not file findings upstream from here

This project publishes findings about the conformance of published documents to
the published specification. It does not open issues or pull requests on NIST,
FedRAMP, or any vendor's repositories, and it does not characterize anyone's
software. A contribution that turns a finding into a bug report about someone
else's tool is out of scope.

## Commit style: Conventional Commits

This repository uses [Conventional Commits](https://www.conventionalcommits.org/):
`<type>[optional scope]: <description>` with types like `feat`, `fix`, `docs`,
`refactor`, `test`, `build`, `ci`, `chore`.

## ADRs: record significant decisions

Any decision that is hard to reverse or that shapes the rule model, the
severity contract, or the vendoring policy gets an Architecture Decision Record
in [`docs/adr/`](docs/adr/) (`NNNN-short-title.md`; see ADR-0000 for the
format). Superseding an earlier decision means marking the old ADR superseded,
not deleting it.

## Pull requests

Open a PR against `main`. The short version of the checklist:

- `make verify` is green.
- No fixture or test data is copied from anyone's real document; fixtures are
  original and synthetic.
- No gate or floor is weakened, and no UNVERIFIABLE becomes a silent pass.
- An ADR is added if you made a significant decision.
- [`CHANGELOG.md`](CHANGELOG.md) `[Unreleased]` is updated for user-visible
  changes.

## License

By contributing, you agree that your contributions are licensed under the
project's [Apache-2.0](LICENSE) license. You must have the right to release
what you contribute, and it must contain no proprietary material.
