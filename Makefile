PY := .venv/bin/python
PORT ?= 8765

.PHONY: install run test cov lint typecheck format audit check smoke docker-build docker-run

install:
	python3 -m venv .venv
	$(PY) -m pip install -q -r requirements-dev.txt

run:
	set -a; [ -f .env ] && . ./.env; set +a; $(PY) -m uvicorn main:app --port $(PORT)

test:
	$(PY) -m pytest -q

cov:
	$(PY) -m pytest -q --cov=core --cov=main --cov-report=term-missing --cov-fail-under=95

lint:
	$(PY) -m ruff check . && $(PY) -m ruff format --check .

typecheck:
	$(PY) -m mypy

format:
	$(PY) -m ruff check --fix . && $(PY) -m ruff format .

audit:
	$(PY) -m pip_audit -r requirements.txt

# Everything CI runs, in one command.
check: lint typecheck cov audit

# Needs a running server: make run, then in another terminal: make smoke
smoke:
	$(PY) scripts/smoke_test.py http://127.0.0.1:$(PORT)

docker-build:
	docker build -t agentledger .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env agentledger
