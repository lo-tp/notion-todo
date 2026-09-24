UV ?= uv

.PHONY: test coverage coverage-html clean

## Run the unit test suite with coverage (terminal report, shows missing lines)
test:
	$(UV) run pytest --cov --cov-report=term-missing

## Run tests and emit both a terminal and an HTML coverage report
coverage:
	$(UV) run pytest --cov --cov-report=term-missing --cov-report=html

## Generate an HTML coverage report from the existing .coverage data
coverage-html:
	$(UV) run coverage html

## Remove coverage and test artifacts
clean:
	rm -rf htmlcov .coverage .coverage.* .pytest_cache
