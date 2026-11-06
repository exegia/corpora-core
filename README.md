# `corpora-template`

<!-- Replace this title and paragraph with your project. Keep the sections below that still apply. -->

A GitHub template with the boring-but-essential parts already wired: SemVer releases driven by Conventional
Commits, CI that adapts to your stack, secrets handling, end-to-end test hooks, and guidance for AI coding agents.
It works the same for **Rust + GPUI, Python, TypeScript, React, Expo, SwiftUI** and projects that **build AI
agents**, and it stays green before you have written any product code.

## What you get

| Area         | What is included                                                                                            |
| ------------ | ----------------------------------------------------------------------------------------------------------- |
| Dev cycle    | One `make` entry point; stack auto-detection; `make doctor`, `setup`, `dev`, `fmt`, `ci`                    |
| CI           | PR gate (`guard`, `check`, `e2e`, `package`), nightly matrix, CodeQL, dependency review                     |
| Releases     | `dev -> next -> release/vX.Y.Z -> main`, SemVer from commits, generated changelog, tags, GitHub Releases    |
| Publishing   | Opt-in PyPI (OIDC), npm (provenance), crates.io, EAS, custom deploy; artifacts attached to releases         |
| Secrets      | gitleaks hook and CI gate, `.env` workflow, push to GitHub secrets, push protection on                      |
| Repo as code | `.github/settings.yml`, branch/tag rulesets, labels, generated Dependabot config                            |
| AI agents    | `AGENTS.md`, `CLAUDE.md`, Copilot instructions, ten skills in `.github/skills/`, validator                  |
| Community    | Issue forms, PR template, `CODEOWNERS`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, MIT license |
| Self-tests   | `make selftest` tests the automation scripts themselves                                                     |

## Quick start

```bash
make doctor     # which tools are missing for the stacks detected here
make setup      # deps, git hooks, .env, commit template, agent skill links
make ci         # exactly what CI runs on a pull request
```

With no manifest present every task is a no-op, so this passes on a fresh copy. Add `pyproject.toml`,
`package.json`, `Cargo.toml` or `Package.swift` and the same commands start running your tools.

### Use it for a new project

1. Click **Use this template** and clone the new repository.
2. Replace this README, `LICENSE` (holder), `SECURITY.md` and `CODE_OF_CONDUCT.md` contacts
   (`REPLACE_ME@example.com`), and `.github/CODEOWNERS`.
3. Create the automation GitHub App and set `AUTOMATION_APP_ID` / `AUTOMATION_APP_PRIVATE_KEY`
   ([details](.github/WORKFLOW.md#2-secrets-and-variables)).
4. `make repo-bootstrap` creates `dev` and `next`, makes `dev` the default branch, and applies settings,
   labels, rulesets and security features.
5. `make setup`, add your first stack manifest, then `make dependabot`.
6. Delete the skills and `.env.example` sections for stacks you do not use. [`TODO.md`](TODO.md) has the full checklist.

## Commands

Every dev and CI step is a target; run `make help` for the full list.

| Task                           | Command                                                                        |
| ------------------------------ | ------------------------------------------------------------------------------ |
| Check tools / first-time setup | `make doctor` / `make setup`                                                   |
| Run the app                    | `make dev`                                                                     |
| Format and autofix / verify    | `make fmt` / `make lint-check`                                                 |
| Types, unit tests, build       | `make typecheck`, `make test`, `make build`                                    |
| End-to-end tests, agent evals  | `make e2e`, `make eval`                                                        |
| Everything CI runs on a PR     | `make ci`                                                                      |
| Release artifacts              | `make pack`                                                                    |
| Test the repo's own automation | `make selftest`                                                                |
| Validate skills / instructions | `make agents-check`                                                            |
| Secrets                        | `make env-init`, `env-check`, `secrets-scan`, `secrets-push`, `secrets-doctor` |
| Versions and releases          | `make bump-info`, `next-version`, `changelog`, `cut-release`                   |
| Repo settings                  | `make settings-apply`, `labels`, `rulesets-apply`, `dependabot`                |

Override any task for any stack: `make test TEST_CMD="pytest -x"`. Force the stack list with
`STACKS="python node"`. Monorepos: only root manifests are detected, so set the overrides.

### Stack detection

| Stack            | Detected by                    | `lint` / `typecheck`                | `test` / `e2e`                                     |
| ---------------- | ------------------------------ | ----------------------------------- | -------------------------------------------------- |
| Python (uv)      | `pyproject.toml`               | ruff; mypy, pyright or ty           | pytest; `tests/e2e/`, evals in `tests/evals/`      |
| TypeScript/React | `package.json`                 | package scripts `lint`, `typecheck` | `test`; `test:e2e` or Playwright                   |
| Expo             | `expo` dependency              | as above                            | Maestro flows in `.maestro/`                       |
| Rust + GPUI      | `Cargo.toml`                   | `cargo fmt`, `clippy -D warnings`   | `cargo test`/nextest; `tests/e2e.rs`               |
| SwiftUI          | `Package.swift` / `.xcodeproj` | SwiftLint, swift-format             | `swift test` / `xcodebuild`; `XCODE_UITEST_TARGET` |

The package manager comes from the lockfile (bun, pnpm, yarn, npm). Swift and GPUI run on macOS runners; set the
`CI_RUNNERS` variable to change that.

## Branching and releases

```text
<type>/<slug> --squash--> dev --promote--> next --cut--> release/vX.Y.Z --draft PR--> main --> vX.Y.Z
```

- Branch from `dev` as `<type>/<slug>` (`feat/123-add-parser`); types: `feat fix chore docs ci refactor test perf build style revert ai`.
- The **PR title** must be a Conventional Commit (`feat(scope)!: summary`). It becomes the squash commit and sets
  the bump: `!` or `BREAKING CHANGE` major, `feat` minor, anything else patch.
- `dev` is promoted to `next` nightly or on demand; a push to `next` cuts `release/vX.Y.Z` with version files and
  a changelog section and opens a draft PR into `main`; merging it tags and publishes the release.

Details: [policy](.github/BRANCH-AND-RELEASE-POLICY.md), [stages](.github/LIFECYCLE.md),
[operations and troubleshooting](.github/WORKFLOW.md).

## Secrets

Credentials must never reach a commit. Three layers:

1. **`.env` is gitignored**; commit `.env.example` with `REPLACE_ME` placeholders. `make env-init` creates `.env`
   with mode 600 and `make env-check` diffs the keys.
2. **gitleaks pre-commit hook** (`make setup` installs it). It is advisory: `--no-verify` skips it, so never use it.
3. **`Secret Scan` workflow** is the real gate. `Detect hardcoded secrets` is a required check on `dev`, `next`
   and `main`; GitHub push protection and secret scanning are switched on by `make settings-apply`.

If a secret leaks: rotate it first, then remove it. To load values into CI use
`make secrets-push ENV_FILE=.env.ci ENVIRONMENT=preview` (names are shown for confirmation, values never printed).
`.gitleaks.toml` allowlists only template placeholders; keep it narrow.

## Testing

- `make test` runs fast unit and integration tests. End-to-end suites (`make e2e`) and agent evals (`make eval`)
  are separate on purpose.
- CI runs e2e on PRs into `next` or `main`, on PRs labelled `run-e2e`, on pushes to `next`, and nightly.
- `make selftest` covers this repository's own scripts (`tests/template/`); it runs inside `make ci`.

## AI agents

| File                              | Role                                                                              |
| --------------------------------- | --------------------------------------------------------------------------------- |
| `AGENTS.md`                       | Canonical rules for every agent; edit this first                                  |
| `CLAUDE.md`                       | Imports `AGENTS.md`, adds Claude Code specifics                                   |
| `.github/copilot-instructions.md` | Short form for GitHub Copilot                                                     |
| `.github/skills/*/SKILL.md`       | Task skills: dev cycle, release flow, secrets, e2e, one per stack, agent building |

`make agents-link` symlinks `.claude/skills` and `.agents/skills` to `.github/skills` (local only);
`make agents-check` validates skills and keeps `CLAUDE.md` importing `AGENTS.md`. Keep these files aligned with
the automation: change them in the same PR.

## Repository layout

```text
.
├── makefile                  one entry point for dev and CI
├── scripts/                  stack runner, versioning, release, secrets, agent assets
├── tests/template/           tests for scripts/ (make selftest)
├── .github/
│   ├── workflows/            pr, secret-scan, security, promote, next, release, publish, matrix, ...
│   ├── actions/setup/        detects stacks, installs only their toolchains
│   ├── rulesets/ settings.yml  branch protection and repo settings as code
│   ├── scripts/              bootstrap-repo, apply-settings, apply-rulesets
│   ├── skills/               agent skills
│   ├── ISSUE_TEMPLATE/ PULL_REQUEST_TEMPLATE.md CODEOWNERS
│   └── WORKFLOW.md LIFECYCLE.md BRANCH-AND-RELEASE-POLICY.md
├── .devcontainer/            Codespaces and dev containers
├── AGENTS.md CLAUDE.md
├── CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md LICENSE TODO.md CHANGELOG.md VERSION
└── .env.example .gitmessage .pre-commit-config.yaml .gitleaks.toml
```

`VERSION` is the fallback version file while no stack manifest declares one; delete it once `pyproject.toml`,
`Cargo.toml`, `package.json` or an Xcode project carries the version.

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. Report vulnerabilities privately as described in
[SECURITY.md](SECURITY.md). Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
Licensed under the [MIT License](LICENSE).
