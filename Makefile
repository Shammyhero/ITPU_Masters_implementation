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

# Verify the SHIPPABLE artifact, not the developer's accumulated venv.
# A working `make test` proves nothing about what `pip install airs-bench` gives
# someone else: this builds a throwaway venv, installs only what pyproject.toml
# declares, and runs lint + the full suite against that. It is how the missing
# langchain-anthropic dependency was found -- agents/llm.py imported it for every
# claude-* model and no extra declared it, so the cross-model arm could not run
# from a clean install.
ci:
	@rm -rf .ci-venv
	@python3 -m venv .ci-venv
	@.ci-venv/bin/pip install -q -e ".[ci]"
	@.ci-venv/bin/python -m ruff check src tests
	@.ci-venv/bin/python -m pytest -q
	@rm -rf .ci-venv
	@echo "clean-install verification passed"
