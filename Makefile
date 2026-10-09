# Travelers World Map. Run from the repository root.
PY ?= python3
export PYTHONPATH := pipeline
BUNDLE ?=
PREVIOUS ?=
ARGS ?=

.PHONY: viewer capitals capitals-pack geofacts tiercal admit help test lint verify release-verify freeze qids qids-apply classes pin-check extract-plan extract extract-pack recall details details-pack profile signal classlabels pageviews pageviews-pack
OUT ?= data/raw/wikidata/$(shell date -u +%F)

help:
	@echo "make test            unit and mutation tests for the gates (must always pass)"
	@echo "make lint            ruff"
	@echo "make verify BUNDLE=  run every gate on a published bundle; exits 1 until it passes"
	@echo "                     (the 'Error 1' make prints is that exit status, not a crash)"
	@echo "make release-verify  also run the holdout and precision gates"
	@echo "make qids             (owner, on the laptop) propose QIDs for the golden set -> data/golden/qid_candidates.csv"
	@echo "make qids-apply      apply the owner decisions in data/golden/qid_decisions.csv"
	@echo "make classes         (owner, on the laptop) check data/rules/classes.csv against Wikidata"
	@echo "make extract-plan     show the Wikidata queries M1 would send (nothing is sent)"
	@echo "make extract OUT=    run the Wikidata prototype extraction for the nine countries (resumable)"
	@echo "make extract-pack OUT=  convert to Parquet and pin in data/inputs/MANIFEST.json"
	@echo "make recall           how many golden places the extraction found (data/golden/s1_recall.md)"
	@echo "make details         (owner, laptop) fetch labels, aliases, part-of and dates for the candidates; resumable"
	@echo "make admit            build the first bundle in build/first and the review lists in data/review"
	@echo "make viewer           open the local viewer on build/first: browse, check rules, label kinds, review precision"
	@echo "make capitals         (owner, laptop) which states each place is or was the capital of (Wikidata P36); resumable"
	@echo "make capitals-pack    convert to Parquet and pin"
	@echo "make geofacts         relief, land cover and distance to the coast per place (public AWS and Natural Earth data); resumable"
	@echo "make pageviews       (owner, laptop) twelve months of English pageviews for the places in build/first; resumable"
	@echo "make pageviews-pack  convert the pageviews to Parquet and pin them"
	@echo "make details-pack    convert the details to Parquet and pin them"
	@echo "make profile         (owner, laptop) fetch which Wikipedias carry each candidate (about 1,700 requests; resumable), then pack"
	@echo "make signal          calibrate the attention signal against the golden set (data/golden/s1_signal.md)"
	@echo "make classlabels     (owner, laptop) labels and parents of the 600 most frequent candidate classes -> data/rules/class_labels.csv"
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

extract-plan:
	$(PY) -m atlas.extract plan

extract:
	$(PY) -m atlas.extract run --out $(OUT)

extract-pack:
	$(PY) -m atlas.extract check --out $(OUT) && $(PY) -m atlas.extract parquet --out $(OUT) && $(PY) -m atlas.extract pin --out $(OUT)

recall:
	$(PY) -m atlas.recall --report data/golden/s1_recall.md

details:
	$(PY) -m atlas.details run

details-pack:
	$(PY) -m atlas.details parquet && $(PY) -m atlas.details pin

profile:
	$(PY) -m atlas.details profile && $(PY) -m atlas.details profile-parquet

admit:
	$(PY) -m atlas.admit && $(PY) -m atlas.review

tiercal:
	$(PY) -m atlas.tiercal --report data/golden/tier_calibration.md

viewer:
	$(PY) -m atlas.viewer

capitals:
	$(PY) -m atlas.capitals run

capitals-pack:
	$(PY) -m atlas.capitals parquet && $(PY) -m atlas.capitals pin

geofacts:
	$(PY) -m atlas.geofacts run && $(PY) -m atlas.geofacts parquet && $(PY) -m atlas.geofacts pin

pageviews:
	$(PY) -m atlas.pageviews run

pageviews-pack:
	$(PY) -m atlas.pageviews parquet && $(PY) -m atlas.pageviews pin

signal:
	$(PY) -m atlas.signal --report data/golden/s1_signal.md

classlabels:
	$(PY) -m atlas.classlabels
