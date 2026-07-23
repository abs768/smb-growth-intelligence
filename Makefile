PY ?= ./.venv/bin/python
export PYTHONPATH := src

.PHONY: help setup generate pipeline features train quality all report clean

help:
	@echo "make setup     - create venv and install dependencies"
	@echo "make all       - run the full platform end-to-end (generate -> pipeline -> features -> train -> quality)"
	@echo "make generate  - regenerate the GA4-shaped raw dataset"
	@echo "make pipeline  - run the SQL ETL models (staging -> intermediate -> marts)"
	@echo "make features  - build the point-in-time feature store"
	@echo "make train     - train + evaluate the propensity model vs baseline"
	@echo "make quality   - run data-quality assertions"
	@echo "make clean     - remove the local warehouse and generated data"

setup:
	python3 -m venv .venv
	./.venv/bin/python -m pip install --upgrade pip
	./.venv/bin/python -m pip install -r requirements.txt

generate:
	$(PY) -m smb.generate_data

pipeline:
	$(PY) -m smb.pipeline.run_models

features:
	$(PY) -m smb.features.build_features

train:
	$(PY) -m smb.features.train

quality:
	$(PY) -m smb.observability.run_checks

all:
	$(PY) -m smb.run

clean:
	rm -f data/warehouse.duckdb
	rm -rf data/raw
