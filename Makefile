.PHONY: setup data etl viz all clean lint tf-validate api api-setup web web-setup

PY ?= ./.venv/bin/python
RISK_THRESHOLD ?= 12
SEED ?= 42

setup:
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -r requirements.txt

data:
	$(PY) generate_mock_data.py --seed $(SEED)

etl:
	$(PY) etl.py --risk-threshold-hours $(RISK_THRESHOLD)

viz:
	$(PY) visualize.py

all: data etl viz

api-setup:
	./.venv/bin/pip install -r api/requirements.txt

api:
	./.venv/bin/uvicorn api.app:app --reload --port 8000

web-setup:
	cd frontend && npm install

web:
	cd frontend && npm start

lint:
	./.venv/bin/ruff check .

tf-validate:
	cd terraform && terraform init -backend=false && terraform validate

clean:
	rm -rf data output dist
