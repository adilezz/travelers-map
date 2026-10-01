# Travelers World Map. Run from the repository root.
PY ?= python3
export PYTHONPATH := pipeline
BUNDLE ?=
PREVIOUS ?=
ARGS ?=

.PHONY: help test lint verify release-verify freeze qids qids-apply classes pin-check

help:
	@echo "make test            unit and mutation tests for the gates (must always pass)"
	@echo "make lint            ruff"
	@echo "make verify BUNDLE=  run every gate on a published bundle; exits 1 until it passes"
	@echo "                     (the 'Error 1' make prints is that exit status, not a crash)"
	@echo "make release-verify  also run the holdout and precision gates"
	@echo "make qids             (owner, on the laptop) propose QIDs for the golden set -> data/golden/qid_candidates.csv"
	@echo "make qids-apply      apply the owner decisions in data/golden/qid_decisions.csv"
	@echo "make classes         (owner, on the laptop) check data/rules/classes.csv against Wikidata"
	@echo "make pin-check       check that every pinned input is present and unchanged"
	@echo "make freeze          freeze the owner-written holdout by hash (see data/holdout/README.md)"
	@echo "ARGS=--prototype     accept skipped checks for a declared prototype build"

test:
	cd pipeline && $(PY) -m pytest -q

lint:
	cd pipeline && $(PY) -m ruff check .

verify:
	$(PY) -m atlas.verify $(if $(BUNDLE),--bundle $(BUNDLE)) $(if $(PREVIOUS),--previous $(PREVIOUS)) $(ARGS)

release-verify:
	$(PY) -m atlas.verify --release $(if $(BUNDLE),--bundle $(BUNDLE)) $(if $(PREVIOUS),--previous $(PREVIOUS)) $(ARGS)

freeze:
	$(PY) -m atlas.freeze

qids:
	$(PY) -m atlas.qids resolve

qids-apply:
	$(PY) -m atlas.qids apply

classes:
	$(PY) -m atlas.qids classes

pin-check:
	$(PY) -m atlas.snapshot check $(ARGS)
