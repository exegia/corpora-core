---
name: stack-python
description: Python conventions with uv - sync, run, lock, ruff, mypy/pyright/ty, pytest markers e2e and eval, src layout, uv build and PyPI trusted publishing. Use when touching pyproject.toml, adding dependencies, fixing lint or type failures, or releasing a Python package.
---

# Python (uv)

**When to use:** any repo with a root `pyproject.toml`: adding deps, running tests, fixing ruff/type errors, building or publishing.

## What CI runs

Detected by `pyproject.toml`. Tools run through uv.

```sh
make install      # uv sync
make fmt          # ruff format + ruff check --fix
make lint-check   # ruff check + ruff format --check
make typecheck    # mypy, pyright, or ty (whichever is configured)
make test         # pytest
make build        # uv build
```

## uv workflow

```sh
uv sync                    # create/update .venv from uv.lock
uv add httpx               # add runtime dep (updates pyproject + uv.lock)
uv add --dev pytest ruff   # dev dependency
uv remove httpx
uv lock                    # refresh lockfile
uv run pytest -x           # run inside the project env
uv run python -m mypkg
```

- Commit `uv.lock`. Never `pip install` into the project env.
- Pin the interpreter with `requires-python` and a `.python-version` file.

## Layout

```
pyproject.toml
src/mypkg/__init__.py
tests/            # unit tests
tests/e2e/        # end-to-end (pytest, marker e2e)
```

Use the `src/` layout so tests import the installed package, not the working directory.

## Lint and types

- Configure ruff in `[tool.ruff]` in `pyproject.toml`; enable at least `E,F,I,UP,B`.
- Pick exactly one type checker as the gate (mypy, pyright, or ty). Start strict on new code.
- Annotate public functions; avoid blanket `# type: ignore` (use a specific code).

## pytest markers

Declare markers in `pyproject.toml` so `--strict-markers` works:

```toml
[tool.pytest.ini_options]
markers = ["e2e: end-to-end tests", "eval: agent/model evaluations"]
addopts = "-m 'not e2e and not eval'"
```

`make e2e` uses `tests/e2e/`; `make eval` runs `-m eval`. Keep both out of the default `make test`.

## Release and publishing

The release script bumps `version` in `pyproject.toml` and `CHANGELOG.md`. `make pack` builds sdist and wheel via `uv build` into `dist/`.

To publish to PyPI, set repo variable `PUBLISH_PYPI` to `true` and configure a PyPI trusted publisher (OIDC) for the repo and release workflow. Prefer trusted publishing over long-lived API tokens; if a token is unavoidable, store it as a GitHub secret only.

## Overrides

`TEST_CMD="uv run pytest -n auto" make test`; `STACKS="python"` to force.

## Pitfalls

- Editing `uv.lock` by hand; use `uv lock`.
- Forgetting to commit lockfile changes after `uv add`.
- Tests passing locally only because the cwd is on `sys.path` (flat layout).
- Unregistered markers silently selecting nothing.
- Secrets in `pyproject.toml` or test fixtures; use env vars.
