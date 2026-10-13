.PHONY: run test stop trial-check trial-models trial trial-test

# Judges invoke this file from the repository root; track files stay in track_2b/.
COMPOSE := docker compose --project-directory track_2b --file track_2b/compose.yaml

run:
	$(COMPOSE) run --rm --no-deps bootstrap
	$(COMPOSE) up --build --detach --wait app worker
	@echo "Open http://localhost:8000. Synthetic credentials: track_2b/.runtime/demo-credentials.txt"

test:
	$(COMPOSE) run --rm --no-deps migrate python src/manage.py test identity records --settings=continuity.test_settings --noinput

trial-check:
	$(COMPOSE) run --rm --no-deps trial python src/intelligence/trial.py check

trial-models:
	$(COMPOSE) run --rm --no-deps trial python src/intelligence/trial.py models

trial:
	$(COMPOSE) run --rm --no-deps trial

trial-test:
	$(COMPOSE) run --rm --no-deps trial python -m unittest discover -s src/intelligence/tests -v

stop:
	$(COMPOSE) down
