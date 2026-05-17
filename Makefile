# Orbit Wars development shortcuts.
# Use `make help` for the list.

PYTHON ?= python3
PRESET ?= blitz

.PHONY: help test test-core test-agents test-build test-eval test-metrics test-viz test-tournament \
        build build-all submit-prep eval pytest pytest-verbose clean

help:
	@echo "Targets:"
	@echo "  make test             run every smoke suite (core/agents/build/eval)"
	@echo "  make test-core        run core/state/geometry smoke tests"
	@echo "  make test-agents      run agent + parity smoke tests"
	@echo "  make test-build       run build-pipeline smoke tests"
	@echo "  make test-eval        run runner smoke tests"
	@echo "  make test-metrics     run metrics + decision-log smoke tests"
	@echo "  make test-viz         run renderer + replay smoke tests"
	@echo ""
	@echo "  make replay REPLAY=path/to.json [OUT=out.html]   render a replay"
	@echo ""
	@echo "  make build PRESET=blitz       build main.py from a YAML preset"
	@echo "  make build-all                build every preset under _build/"
	@echo "  make submit-prep PRESET=blitz build main.py and print kaggle cmd"
	@echo ""
	@echo "  make eval ARGS=\"preset:blitz random -n 20 -p 4 -o out.jsonl\""
	@echo "                                 run the parallel evaluator"
	@echo ""
	@echo "  make clean            remove generated build/eval artifacts"

test: test-core test-agents test-build test-eval test-metrics test-viz test-tournament

test-core:
	$(PYTHON) tests/smoke_test_core.py

test-agents:
	$(PYTHON) tests/smoke_test_agents.py

test-build:
	$(PYTHON) tests/smoke_test_build.py

test-eval:
	$(PYTHON) tests/smoke_test_eval.py

test-metrics:
	$(PYTHON) tests/smoke_test_metrics.py

test-viz:
	$(PYTHON) tests/smoke_test_viz.py

test-tournament:
	$(PYTHON) tests/smoke_test_tournament.py

# pytest entrypoint -- runs every smoke_test_*.py through pytest's
# collector with proper assertion reporting, parametrisation visibility,
# and standard JUnit-friendly exit codes. Requires `pip install pytest`.
pytest:
	$(PYTHON) -m pytest

pytest-verbose:
	$(PYTHON) -m pytest -v -s

build:
	$(PYTHON) tools/build_submission.py $(PRESET) --output main.py

build-all:
	@mkdir -p _build
	@for p in blitz sentinel sniper; do \
		echo "--- building $$p ---"; \
		$(PYTHON) tools/build_submission.py $$p --output _build/$$p.py; \
	done

submit-prep:
	$(PYTHON) tools/build_submission.py $(PRESET) --output main.py
	@echo "Ready to submit:"
	@echo "  kaggle competitions submit orbit-wars -f main.py -m \"$(PRESET) auto-build\""

# Pass-through to tools/eval.py via ARGS, e.g.
#   make eval ARGS="preset:blitz preset:sniper -n 20 -p 4 -o out.jsonl"
eval:
	$(PYTHON) tools/eval.py $(ARGS)

clean:
	rm -rf _build
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Render a kaggle replay JSON into an HTML timeline.
# Usage: make replay REPLAY=replays/abc.json OUT=replay.html
REPLAY ?=
OUT ?= replay.html

.PHONY: replay
replay:
	@if [ -z "$(REPLAY)" ]; then 		echo "usage: make replay REPLAY=path/to/replay.json [OUT=out.html]"; 		exit 1; 	fi
	$(PYTHON) tools/replay.py $(REPLAY) -o $(OUT) --show-orbits
