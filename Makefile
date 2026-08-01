PY := .venv/bin/python

.PHONY: setup test lint grid up down demo data-ecommerce data-airline

setup:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check src tests

grid:
	$(PY) -m airsbench.runner.run --grid --dry-run

up:
	docker compose up -d

down:
	docker compose down

demo:
	npm --prefix demo run dev

data-ecommerce:
	$(PY) -m airsbench.dataprep.prepare_ecommerce --out data/ecommerce

data-airline:
	$(PY) -m airsbench.dataprep.prepare_airline --out data/airline
