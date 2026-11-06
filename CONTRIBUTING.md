# Contributing

Thanks for helping out. This guide covers the workflow for humans and AI agents
alike. By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Quick start

```sh
git clone <your fork or this repo>
cd <repo>
make doctor   # check required tools
make setup    # install deps + pre-commit hooks (incl. commit-msg, pre-push) + commit template
make ci       # run everything CI runs on a PR
```

Run `make setup` once per clone. Run `make help` to list all targets.

## Branches

Branch from `dev` (the default branch). Name branches `<type>/<slug>`:

| Type       | Use for                               | Example                  |
| ---------- | ------------------------------------- | ------------------------ |
| `feat`     | New functionality                     | `feat/123-add-parser`    |
| `fix`      | Bug fixes (also hotfixes)             | `fix/null-config-crash`  |
| `chore`    | Maintenance, tooling                  | `chore/bump-deps`        |
| `docs`     | Documentation only                    | `docs/contributing`      |
| `ci`       | CI/CD and automation                  | `ci/cache-cargo`         |
| `refactor` | Behavior-preserving code changes      | `refactor/split-module`  |
| `test`     | Tests only                            | `test/parser-edge-cases` |
| `perf`     | Performance improvements              | `perf/lazy-load-index`   |
| `build`    | Build system and dependencies         | `build/switch-bundler`   |
| `style`    | Formatting, no logic change           | `style/fmt-pass`         |
| `revert`   | Reverting an earlier change           | `revert/bad-migration`   |
| `ai`       | Agent prompts, skills, AI config      | `ai/update-agents-md`    |

Flow: feature branch -> PR into `dev` (squash-merged) -> `dev` is promoted to
`next` automatically -> a push to `next` cuts `release/vX.Y.Z` with a draft PR
into `main` -> merging it tags `vX.Y.Z` and publishes a GitHub Release.
`main` is only updated through that release PR. Do not push to `main`, `next`,
or `dev` directly.

Hotfix: open a normal `fix/<slug>` PR into the in-flight `release/vX.Y.Z`
branch.

Details: [`.github/BRANCH-AND-RELEASE-POLICY.md`](.github/BRANCH-AND-RELEASE-POLICY.md),
[`.github/LIFECYCLE.md`](.github/LIFECYCLE.md),
[`.github/WORKFLOW.md`](.github/WORKFLOW.md).

## Commits

Use Conventional Commits, imperative mood, subject up to 72 characters. The body
explains why, not what. `make setup` configures `.gitmessage` as the template.

## Pull request titles

The PR title must be a Conventional Commit, because the squash commit subject
equals the PR title:

```text
<type>(optional-scope)!: summary
```

Examples:

```text
feat(parser): add streaming tokenizer
fix: handle empty config file
docs(readme): document make targets
refactor(api)!: rename Client::open to Client::connect
```

### How the version is derived

| PR title / footer                          | Bump  |
| ------------------------------------------ | ----- |
| `!` after type/scope, or `BREAKING CHANGE:` footer | major |
| `feat`                                     | minor |
| Everything else (`fix`, `chore`, `docs`, ...) | patch |

## Pull request checklist

- [ ] Title is a valid Conventional Commit
- [ ] `make ci` passes locally
- [ ] Tests added or updated
- [ ] Docs and `AGENTS.md` updated if workflow or conventions changed
- [ ] No secrets or `.env` files committed
- [ ] Breaking changes marked with `!` or a `BREAKING CHANGE:` footer
- [ ] Linked issue (`Closes #123`) when one exists

## Tests

```sh
make test        # unit and integration tests
make e2e         # end-to-end tests
make lint-check  # lint without modifying files
make typecheck   # type checks
make fmt         # format code
make ci          # all of the above, as CI runs them
```

## Secrets

- Never commit credentials, tokens, or API keys, including in tests, fixtures,
  and examples.
- Real values live in `.env` (gitignored). Commit `.env.example` with
  placeholders. Use `make env-init` and `make env-check`.
- `gitleaks` runs as a pre-commit hook and as the `Secret Scan` CI workflow.
  Run it manually with `make secrets-scan`.
- Never bypass hooks with `--no-verify`. If a secret was committed, rotate it
  first, then remove it. See [SECURITY.md](SECURITY.md).

## Where docs live

| Doc                                                                     | Purpose                     |
| ----------------------------------------------------------------------- | --------------------------- |
| [`README.md`](README.md)                                                | Overview and setup          |
| [`AGENTS.md`](AGENTS.md)                                                | Guidance for AI agents      |
| [`.github/WORKFLOW.md`](.github/WORKFLOW.md)                            | Operations guide            |
| [`.github/BRANCH-AND-RELEASE-POLICY.md`](.github/BRANCH-AND-RELEASE-POLICY.md) | Branch and release policy |
| [`.github/LIFECYCLE.md`](.github/LIFECYCLE.md)                          | Lifecycle stage table       |
| [`SECURITY.md`](SECURITY.md)                                            | Vulnerability reporting     |
| [`TODO.md`](TODO.md)                                                    | Living backlog              |
| [`CHANGELOG.md`](CHANGELOG.md)                                          | Generated at release cut    |

## Recording decisions

For significant architectural or process decisions, add an Architecture Decision
Record under `docs/adr/` (optional), for example `docs/adr/0001-use-uv.md`, with
context, decision, and consequences. Link it from the PR.

## Reporting issues

Use the issue forms: bug report, feature request, or task. Report
vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
