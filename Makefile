PY ?= ../nina/bin/python
PIP ?= ../nina/bin/pip

.PHONY: install migrate-shared migrate run worker beat test lint fmt seed

install:
	$(PIP) install -r requirements/dev.txt

migrate-shared:
	$(PY) manage.py migrate_schemas --shared

migrate:
	$(PY) manage.py migrate_schemas

run:
	$(PY) manage.py runserver 0.0.0.0:8000

worker:
	../nina/bin/celery -A config worker -l info

beat:
	../nina/bin/celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler

test:
	../nina/bin/pytest

lint:
	../nina/bin/ruff check .

fmt:
	../nina/bin/ruff check --fix . && ../nina/bin/black . && ../nina/bin/isort .

seed:
	$(PY) manage.py seed_demo
