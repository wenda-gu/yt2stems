.PHONY: test lint build check clean release-sha256

test:
	python -m unittest

lint:
	ruff check .

build:
	python -m build

check: lint test build

clean:
	rm -rf build dist src/yt2stems/__pycache__ tests/__pycache__

release-sha256:
	shasum -a 256 dist/*
