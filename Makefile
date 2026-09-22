PY := .venv/bin/python

.PHONY: setup test lint grid up down demo data-ecommerce data-airline ci web dist-check figures lock

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
	docker compose -f infra_unused/docker-compose.yml up -d

down:
	docker compose -f infra_unused/docker-compose.yml down

# The console's Next.js dev server on :3000. Run `airs serve --dev` beside it for the API.
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

# Build the web console into the package, where `airs serve` finds it and the wheel
# ships it (src/airsbench/web/, gitignored). Node is needed here, once, at build
# time; nobody installing the wheel needs it. demo/src/data/aist.json is committed,
# so this works from a clone without the datasets (`npm --prefix demo run data`
# regenerates that file from results/runs/ when the evidence changes).
# Refuses while `next dev` runs: a build then corrupts demo/.next. The [n] keeps
# pgrep from matching this recipe's own shell.
web:
	@if pgrep -f "[n]ext dev" >/dev/null; then \
		echo 'make web: stop "next dev" first -- building while it runs corrupts demo/.next'; \
		exit 1; fi
	@npm --prefix demo ci --no-audit --no-fund --loglevel=error
	@rm -rf demo/.next demo/out
	@npm --prefix demo run build
	@rm -rf src/airsbench/web
	@cp -R demo/out src/airsbench/web
	@echo "web console built into src/airsbench/web/ ($$(find src/airsbench/web -type f | wc -l | tr -d ' ') files)"

# Verify the WHEEL, not the source tree. `make ci` installs editable, so a file
# missing from the built distribution is invisible to it -- which is how a wheel
# that shipped without calibrated_weights.json went unnoticed. This builds the
# wheel, installs it NON-editable into a throwaway venv, and runs the installed
# `airs` command from outside the source tree against the shipped examples,
# checking the exit codes a pipeline step relies on, then starts the installed
# `airs serve` and requires the API and the real console. It needs the network
# once, for the build backend; the installed tool itself never does.
DIST := .dist-check
AIRS := cd $(DIST) && venv/bin/airs
EX := $(CURDIR)/examples
dist-check:
	@test -f src/airsbench/web/index.html || { \
		echo 'dist-check: the web console is not built; run "make web" first, or the wheel ships without it'; \
		exit 1; }
	@rm -rf $(DIST) build
	@python3 -m venv $(DIST)/venv
	@$(DIST)/venv/bin/pip wheel -q --disable-pip-version-check --no-deps -w $(DIST)/wheel .
	@rm -rf build
	@$(DIST)/venv/bin/pip install -q --disable-pip-version-check $(DIST)/wheel/*.whl
	@cd $(DIST) && venv/bin/python -c "import airsbench, sys; \
		sys.exit(f'airsbench came from {airsbench.__file__}, not the wheel') \
		if 'site-packages' not in airsbench.__file__ else None"
	@$(AIRS) --version
	@$(AIRS) probe --records $(EX)/probe/degraded.jsonl --source $(EX)/probe/source.jsonl \
		--task retrieval --json >/dev/null
	@$(AIRS) gate --records $(EX)/probe/healthy.jsonl --source $(EX)/probe/source.jsonl \
		--policy $(EX)/gate/retrieval.json >/dev/null
	@$(AIRS) gate --records $(EX)/probe/degraded.jsonl --source $(EX)/probe/source.jsonl \
		--policy $(EX)/gate/retrieval.json >/dev/null; \
		test $$? -eq 1 || { echo "dist-check: a degraded batch was not refused (exit 1)"; exit 1; }
	@cd $(DIST) && venv/bin/python -c "import yaml" || { echo "dist-check: PyYAML is not installed with the wheel"; exit 1; }
	@$(AIRS) sources sample demo-stale --seed 7 --json >/dev/null
	@cd $(DIST) && venv/bin/python $(CURDIR)/tests/dist_smoke.py venv/bin/airs $(EX)
	@rm -rf $(DIST)
	@echo "wheel verification passed"

# Regenerate every figure the thesis uses. Chapter 4 is written against these,
# so they are built as each analysis lands rather than at the end (docs/plan.md).
figures:
	@mkdir -p docs/figures
	@.venv/bin/python -m airsbench.analysis.curve_sensitivity \
		--figure docs/figures/fig4_7_curve_sensitivity.png >/dev/null
	@.venv/bin/python -m airsbench.analysis.interaction \
		--figure docs/figures/fig4_6_interaction.png >/dev/null
	@.venv/bin/python -m airsbench.analysis.figures >/dev/null
	@.venv/bin/python -m airsbench.analysis.fragility \
		--figure docs/figures/fig4_8_fragility.png >/dev/null
	@.venv/bin/python -m airsbench.analysis.power \
		--figure docs/figures/fig3_1_power.png >/dev/null
	@.venv/bin/python -m airsbench.analysis.verifier_agreement \
		--figure docs/figures/fig4_10_verifier_agreement.png >/dev/null
	@.venv/bin/python -m airsbench.analysis.refetch \
		--figure docs/figures/fig4_9_refetch.png >/dev/null
	@echo "figures written to docs/figures/"

# Pin the exact environment that produced the published results.
# Distinct from `make ci`: ci tests what pyproject.toml DECLARES (unpinned), lock
# records what actually RAN. The package's own line is excluded -- pip freeze
# records it as an editable git+ssh URL tied to the author's credentials.
lock:
	@{ echo "# requirements-lock.txt -- the exact environment that produced the published results."; \
	   echo "# Generated by 'make lock' on $$(date +%Y-%m-%d) from .venv: Python $$(.venv/bin/python -c 'import platform,sys; print(sys.version.split()[0], platform.machine())')."; \
	   echo "# Install: python3.13 -m venv .venv && .venv/bin/pip install -r requirements-lock.txt && .venv/bin/pip install -e . --no-deps"; \
	   echo "# This pins what produced the numbers. 'make ci' separately verifies what pyproject.toml declares."; \
	   .venv/bin/pip freeze | grep -vE '^-e |@ file://|git\+'; \
	 } > requirements-lock.txt
	@echo "requirements-lock.txt: $$(grep -vc '^#' requirements-lock.txt) pinned packages"
