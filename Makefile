.PHONY: all env omnet smoke run test lint

JOBS ?= 2

all: omnet

env:
	uv sync --extra dev --locked

omnet: env
	.venv/bin/python scripts/build_omnet.py --jobs $(JOBS)

smoke: omnet
	.venv/bin/propagation-lab --smoke

run: omnet
	.venv/bin/streamlit run app.py

test: omnet
	.venv/bin/python -m pytest

lint: env
	.venv/bin/ruff check src tests scripts app.py
