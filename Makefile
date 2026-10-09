.PHONY: test lint type cov check install dev-install clean

test:
	pytest -xvs

test-cov:
	pytest --cov=wallexbot --cov-report=term-missing --cov-report=html

lint:
	ruff check src tests

lint-fix:
	ruff check --fix src tests

format:
	ruff format src tests

format-check:
	ruff format --check src tests

type:
	mypy src

cov:
	pytest --cov=wallexbot --cov-report=term-missing --cov-fail-under=90

check: lint format-check type cov

install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"

ui-install:
	pip install -e ".[ui]"

clean:
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache .hypothesis dist build *.egg-info

# Run the bot CLI
run:
	wallexbot --help

# Quick smoke test
smoke:
	pytest tests/unit/test_smoke.py -xvs