.PHONY: setup export audit test clean
PY := .venv/bin/python

setup:
	python3.12 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt

export:          ## regenerate row-level predictions from the model repo (gitignored)
	$(PY) -m src.auditor.export

audit:
	$(PY) -m src.auditor.audit

test:
	$(PY) -m pytest tests/ -q

clean:
	rm -rf reports/*.csv reports/*.json data/*.parquet
