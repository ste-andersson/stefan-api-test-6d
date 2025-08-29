# Simple Makefile for local dev
PY=python3.13

install:
	$(PY) -m ensurepip --upgrade || true
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

run:
	uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

dev: run

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache dist build *.egg-info

.PHONY: install run dev clean
