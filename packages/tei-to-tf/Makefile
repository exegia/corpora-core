.PHONY: check fmt test build
check:
	uv run --locked ruff check .
	uv run --locked ruff format --check .
	uv run --locked mypy --config-file pyproject.toml src
	uv run --locked pytest -q
fmt:
	uv run --locked ruff format .
	uv run --locked ruff check --fix .
test:
	uv run --locked pytest -q
build:
	uv build --out-dir dist
