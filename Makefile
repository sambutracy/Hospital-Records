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
