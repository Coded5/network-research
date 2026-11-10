.PHONY: all env ns3 smoke run test lint

JOBS ?= 2

all: ns3

env:
	uv sync --extra dev --locked

ns3: env
	.venv/bin/python scripts/build_ns3.py --jobs $(JOBS)

smoke: ns3
	.venv/bin/propagation-lab --smoke

run: ns3
	.venv/bin/streamlit run app.py

test: ns3
	.venv/bin/python -m pytest

lint: env
	.venv/bin/ruff check src tests scripts app.py
