# make verify reproduces the full merge-blocking gate set locally, byte for
# byte with CI: ci.yml runs this exact target. Run it before opening a PR.
.PHONY: verify sync lint format typecheck test audit coverage-doc rerecord-walkthrough clean

verify: sync lint format typecheck test audit
	@echo "make verify: all gates passed."

# `uv lock --check` is the drift gate; `--frozen` is not one, and it is worth
# saying why because the two look interchangeable. `--frozen` installs from
# uv.lock without reading pyproject.toml at all, so a lock that no longer
# agrees with the manifest installs cleanly and exits 0. Measured on a scratch
# project with a deliberately stale lock: `uv lock --check` and
# `uv sync --locked` exit 1, `uv sync --frozen` exits 0. The check runs first,
# before any `uv run` in this file, because a bare `uv run` re-locks silently
# and would repair the drift on its way past. The sync itself uses `--locked`
# so the install cannot pass on a stale lock either, even if it is invoked on
# its own without the check ahead of it.
sync:
	uv lock --check
	uv sync --locked

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

typecheck:
	uv run mypy

test:
	uv run pytest --cov --cov-report=term-missing

# Dependency vulnerability audit over the locked environment. The project has
# zero runtime dependencies, so this audits the locked dev toolchain; the
# local package itself is not on PyPI and is reported as skipped, not failed.
audit:
	uv run pip-audit

# Regenerate the published constraint-coverage table from the vendored
# metaschema files. tests/test_constraint_coverage.py fails if it is stale.
coverage-doc:
	uv run python tools/constraint_coverage.py docs/CONSTRAINT-COVERAGE.md

# Re-record the walkthrough cassette. This is the ONLY target here that spends
# money and reaches the network, so it is never part of `verify` and is never
# run by CI. It needs credentials for the account named in
# tests/cassettes/pending-rerecord.json.
#
# The recording is keyed by a hash of the exact prompt, so it has to be made at
# the commit whose prompt it is meant to answer.
#
#   AWS_REGION=<region> make rerecord-walkthrough
#
# RERECORD_MODEL is pinned rather than left to the provider default so that
# successive recordings stay comparable to the one they replace: the cassette
# records the model that answered, and a re-record that silently landed on a
# different model would change the artifact and the reason for the change at
# the same time. Override it deliberately, not by drifting.
#
# The call writes to a temporary cassette and only replaces the committed one
# once it has succeeded, so a failed or refused call leaves the existing
# recording intact rather than destroying it on the way out.
#
# Afterwards, delete the walkthrough entry from
# tests/cassettes/pending-rerecord.json. The suite fails while a fresh cassette
# still carries a stale-declaration, so this is not a step that can be
# forgotten silently. Then run `make verify` and commit both files together.
RERECORD_MODEL ?= global.anthropic.claude-sonnet-4-6
RERECORD_CASSETTE := tests/cassettes/walkthrough-nist-ssp.json
RERECORD_TMP := tests/cassettes/.walkthrough-nist-ssp.recording.json

rerecord-walkthrough:
	@test -n "$$AWS_REGION" || { echo "AWS_REGION is not set; see the comment above this target."; exit 2; }
	@rm -f $(RERECORD_TMP)
	OSCAL_VALIDATE_AI_PROVIDER=bedrock \
	OSCAL_VALIDATE_AI_MODEL=$(RERECORD_MODEL) \
	OSCAL_VALIDATE_AI_CASSETTE=$(RERECORD_TMP) \
	OSCAL_VALIDATE_AI_RECORD=1 \
	uv run oscal-validate walkthrough tests/fixtures/nist_ssp_example.json --format json > /dev/null
	@test -s $(RERECORD_TMP) || { echo "no recording was written; the committed cassette is untouched."; rm -f $(RERECORD_TMP); exit 1; }
	@mv $(RERECORD_TMP) $(RERECORD_CASSETTE)
	@echo "recorded with $(RERECORD_MODEL). Now remove the walkthrough entry from tests/cassettes/pending-rerecord.json."

clean:
	rm -rf .coverage .pytest_cache .mypy_cache .ruff_cache dist build
