UV ?= uv

.PHONY: test coverage coverage-html lint typecheck format check clean

## Run the unit test suite with coverage (terminal report, shows missing lines)
test:
	$(UV) run pytest --cov --cov-report=term-missing

## Run tests and emit both a terminal and an HTML coverage report
coverage:
	$(UV) run pytest --cov --cov-report=term-missing --cov-report=html

## Generate an HTML coverage report from the existing .coverage data
coverage-html:
	$(UV) run coverage html

## Lint with ruff
lint:
	$(UV) run ruff check

## Auto-fix lint issues
lint-fix:
	$(UV) run ruff check --fix

## Format with ruff
format:
	$(UV) run ruff format

## Type-check with pyright
typecheck:
	$(UV) run pyright sync scripts tests

## Lint + type-check together
check:
	$(UV) run ruff check
	$(UV) run pyright sync scripts tests

## Remove coverage and test artifacts
clean:
	rm -rf htmlcov .coverage .coverage.* .pytest_cache
