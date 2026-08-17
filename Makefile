# make verify reproduces the full merge-blocking gate set locally, byte for
# byte with CI: ci.yml runs this exact target. Run it before opening a PR.
.PHONY: verify sync lint format typecheck test audit coverage-doc clean

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

clean:
	rm -rf .coverage .pytest_cache .mypy_cache .ruff_cache dist build
