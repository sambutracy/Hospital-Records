.PHONY: run test stop trial-check trial-models trial trial-test evaluate evaluate-live

# Judges invoke this file from the repository root; track files stay in track_2b/.
BASE_COMPOSE := docker compose --project-directory track_2b --file track_2b/compose.yaml
MODEL_MODE ?= local
APP_PORT ?= 8000
APP_HOST ?= localhost
ifeq ($(MODEL_MODE),local)
COMPOSE := $(BASE_COMPOSE) --file track_2b/compose.local.yaml
else ifeq ($(MODEL_MODE),external)
COMPOSE := $(BASE_COMPOSE)
else
$(error MODEL_MODE must be local or external)
endif

run:
	$(BASE_COMPOSE) run --rm --no-deps bootstrap
ifeq ($(MODEL_MODE),local)
	$(COMPOSE) run --rm --no-deps model-prepare
endif
	$(COMPOSE) up --build --detach --wait app worker
	@echo "Open http://$(APP_HOST):$(APP_PORT). Synthetic credentials: track_2b/.runtime/demo-credentials.txt"

test:
	$(BASE_COMPOSE) run --rm --no-deps migrate python src/manage.py test identity records --settings=continuity.test_settings --noinput

trial-check:
	$(COMPOSE) run --rm --no-deps trial python src/intelligence/trial.py check

trial-models:
	$(COMPOSE) run --rm --no-deps trial python src/intelligence/trial.py models

trial:
	$(COMPOSE) run --rm --no-deps trial

trial-test:
	$(COMPOSE) run --rm --no-deps trial python -m unittest discover -s src/intelligence/tests -v

evaluate:
	$(BASE_COMPOSE) run --rm --no-deps --user 0 --volume ./track_2b/data:/app/data:ro --volume ./track_2b/.runtime/evaluation:/app/.runtime/evaluation migrate python src/manage.py evaluate_records

evaluate-live:
	$(COMPOSE) run --rm --no-deps --user 0 --volume ./track_2b/data:/app/data:ro --volume ./track_2b/.runtime/evaluation:/app/.runtime/evaluation worker python src/manage.py evaluate_records --live

stop:
	$(COMPOSE) down

# Synthetic evaluation has its own database, realm and volumes. See the guide;
# it reuses the prepared local Apertus inference service only.
PYTHON ?= python
PROFILE ?= smoke
ECOSYSTEM := $(PYTHON) track_2b/src/tools/ecosystem.py
.PHONY: ecosystem-prepare ecosystem-plan ecosystem-start ecosystem-seed ecosystem-verify ecosystem-workflows ecosystem-journeys ecosystem-extract ecosystem-model ecosystem-evaluate ecosystem-report
ecosystem-prepare:
	$(ECOSYSTEM) prepare
ecosystem-plan:
	$(ECOSYSTEM) plan --profile $(PROFILE)
ecosystem-start:
	$(ECOSYSTEM) start
ecosystem-seed:
	$(ECOSYSTEM) seed --profile $(PROFILE) --max-documents 64
ecosystem-verify:
	$(ECOSYSTEM) verify --profile $(PROFILE)
ecosystem-workflows:
	$(ECOSYSTEM) workflows --profile $(PROFILE)
ecosystem-journeys:
	$(ECOSYSTEM) journeys --profile $(PROFILE)
ecosystem-extract:
	$(ECOSYSTEM) process --profile $(PROFILE) --max-jobs 32
ecosystem-model:
	$(ECOSYSTEM) process --profile $(PROFILE) --live --max-jobs 4
ecosystem-evaluate:
	$(ECOSYSTEM) evaluate --profile $(PROFILE) --live --max-jobs 1
ecosystem-report:
	$(ECOSYSTEM) report --profile $(PROFILE)
