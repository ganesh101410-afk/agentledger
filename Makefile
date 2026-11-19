PY := .venv/bin/python
PORT ?= 8765

.PHONY: install run test lint format

install:
	python3 -m venv .venv
	$(PY) -m pip install -q -r requirements-dev.txt

run:
	set -a; [ -f .env ] && . ./.env; set +a; $(PY) -m uvicorn main:app --port $(PORT)

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check .

format:
	$(PY) -m ruff check --fix . && $(PY) -m ruff format .
