---
name: dev-cycle
description: Local development loop for this template - make doctor, setup, dev, fmt, ci, stack auto-detection and TASK_CMD overrides. Use when asked how to build, test, lint, run the project, set up a machine, or why make ci fails or does nothing.
---

# Local dev cycle

**When to use:** starting work on a fresh clone, running checks before a PR, or when a task unexpectedly does nothing or runs the wrong tool.

## The loop

```sh
make help      # list every target
make doctor    # verify tools exist for the detected stacks
make setup     # deps + git hooks + .env + commit template + agent skill symlinks
make dev       # run the dev server / app
make fmt       # apply formatters and autofix
make ci        # same steps CI runs
```

Then open the PR (see `branch-and-release`). `make ci` = install + selftest + agents-check + lint-check + typecheck + test + build.

Other targets: `make install`, `make lint-check`, `make typecheck`, `make test`, `make e2e`, `make eval`, `make build`, `make pack` (release artifacts into `dist/`), `make clean`, `make clean-all`.

Every CI step is a make target, so a local green `make ci` predicts a green `check`.

## Stack detection

`scripts/stack.sh list|tags|run <task>` inspects root files:

| Stack | Detected by | Runs |
| --- | --- | --- |
| `python` | `pyproject.toml` | uv, ruff, mypy/pyright/ty, pytest, `uv build` |
| `node` | `package.json` | package.json scripts via bun/pnpm/yarn/npm (from lockfile) |
| `rust` | `Cargo.toml` | cargo fmt, clippy -D warnings, test/nextest, build |
| `swift` | `Package.swift`, `.xcodeproj`, `.xcworkspace` | swift build/test or xcodebuild |

Node flavors (typescript, react, expo) and rust flavor `gpui` come from dependencies. Check with:

```sh
scripts/stack.sh list
scripts/stack.sh tags
```

If no stack is detected, every task is a clean no-op (success, nothing run).

## Overrides

- Any task: set `<TASK>_CMD`, for example `TEST_CMD="pytest -x"`, `BUILD_CMD="make -C app build"`, `PACK_CMD="..."`.
- Force stacks: `STACKS="python node" make ci`.
- Use overrides for one-off runs; commit permanent ones into the workflow or Makefile environment, not into code.

## Monorepos

Detection reads root manifests only. For nested packages either add root-level scripts that delegate (for example a root `package.json` `test` script that runs workspace tests) or set `<TASK>_CMD` overrides and `STACKS`. Do not expect `apps/*/Cargo.toml` to be found.

## Pitfalls

- A task silently skipping means no manifest at the repo root, or the package.json script is missing (`lint`, `typecheck`, `test`, `test:e2e`, `build`, `dev`, `eval`).
- Run `make doctor` before blaming code; missing toolchains are the usual cause.
- Do not run formatters ad hoc with different versions; use `make fmt`.
- `make fmt` modifies files; `make lint-check` never does.
- Swift tasks need a macOS runner; see `stack-swiftui`.
