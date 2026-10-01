# Travelers World Map. Run from the repository root.
PY ?= python3
export PYTHONPATH := pipeline
BUNDLE ?=
PREVIOUS ?=
ARGS ?=

.PHONY: help test lint verify release-verify

help:
	@echo "make test            unit and mutation tests for the gates (must always pass)"
	@echo "make lint            ruff"
	@echo "make verify BUNDLE=  run every gate on a published bundle; exits 1 until it passes"
	@echo "                     (the 'Error 1' make prints is that exit status, not a crash)"
	@echo "make release-verify  also run the holdout and precision gates"
	@echo "ARGS=--prototype     accept skipped checks for a declared prototype build"

test:
	cd pipeline && $(PY) -m pytest -q

lint:
	cd pipeline && $(PY) -m ruff check .

verify:
	$(PY) -m atlas.verify $(if $(BUNDLE),--bundle $(BUNDLE)) $(if $(PREVIOUS),--previous $(PREVIOUS)) $(ARGS)

release-verify:
	$(PY) -m atlas.verify --release $(if $(BUNDLE),--bundle $(BUNDLE)) $(if $(PREVIOUS),--previous $(PREVIOUS)) $(ARGS)
