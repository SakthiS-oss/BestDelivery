.PHONY: install-backend install-frontend backend frontend dev seed test

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

install-backend:
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt

install-frontend:
	cd frontend && npm install

backend:
	cd backend && PYTHONPATH=. ../$(PY) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev -- --host 127.0.0.1 --port 5173

seed:
	$(PY) scripts/seed_demo.py

dev:
	./scripts/dev.sh

test:
	$(PY) -m pytest
