# Agent operating guide

This is the canonical guide for every coding agent (Claude, Copilot, Codex, Zed, Cursor) working in this
repository. `CLAUDE.md` imports it and `.github/copilot-instructions.md` mirrors the essentials, so edit
**this** file first.

This repository is a **generic template** for projects built with Rust + GPUI, Python, TypeScript, React,
Expo, SwiftUI, and AI-agent projects. In a generated repository, replace the placeholders marked
`REPLACE_ME` and trim this file to the stacks the project really uses.

## Do this first

1. `make doctor` - tells you which tools are missing for the stacks detected here.
2. `make setup` - installs dependencies, git hooks, `.env`, the commit template and agent skill links.
3. Read the skill that matches your task in `.github/skills/` (index below).
4. Before finishing: `make fmt` then `make ci`. Report what you actually ran.

## Commands

Every command is a `make` target; each delegates to `scripts/stack.sh`, which detects the stack from the
manifests in the repo (`pyproject.toml`, `package.json`, `Cargo.toml`, `Package.swift`/Xcode project).
With no stack detected every task is a clean no-op.

| Task                                        | Command                                     |
| ------------------------------------------- | ------------------------------------------- |
| Check tools / first-time setup              | `make doctor` / `make setup`                |
| Run the app or dev server                   | `make dev`                                  |
| Format and autofix / verify only            | `make fmt` / `make lint-check`              |
| Type check, unit tests, build               | `make typecheck`, `make test`, `make build` |
| End-to-end tests, agent evals               | `make e2e`, `make eval`                     |
| Everything CI runs on a PR                  | `make ci`                                   |
| Tests for this repo's own automation        | `make selftest`                             |
| Validate skills and agent instruction files | `make agents-check`                         |
| Scan for secrets                            | `make secrets-scan`                         |
| Release artifacts                           | `make pack`                                 |

Override any task for any stack with `<TASK>_CMD` (`make test TEST_CMD="pytest -x"`); force the stack list
with `STACKS="python node"`. Monorepos: only root manifests are detected, so set the overrides.

## Stacks

| Stack            | Detected by                        | Lint / types                      | Tests / e2e                                                     |
| ---------------- | ---------------------------------- | --------------------------------- | --------------------------------------------------------------- |
| Python (uv)      | `pyproject.toml`                   | ruff, mypy / pyright / ty         | pytest; e2e in `tests/e2e/`, evals in `tests/evals/`            |
| TypeScript/React | `package.json` (+ `tsconfig.json`) | scripts `lint`, `typecheck`       | `test`; e2e: `test:e2e` or Playwright                           |
| Expo             | `expo` dependency                  | as above, `expo-doctor`           | e2e: Maestro flows in `.maestro/`                               |
| Rust + GPUI      | `Cargo.toml` (`gpui` dependency)   | `cargo fmt`, `clippy -D warnings` | `cargo test` / nextest; e2e: `tests/e2e.rs`                     |
| SwiftUI          | `Package.swift` / `.xcodeproj`     | SwiftLint, swift-format           | `swift test` / `xcodebuild`; UI tests via `XCODE_UITEST_TARGET` |

The package manager is read from the lockfile (bun, pnpm, yarn, npm). Swift and GPUI jobs run on macOS
runners. Each stack has a skill with the conventions and pitfalls.

## Non-negotiable rules

1. **Never commit a credential**, token, key or `.env` - not in code, tests, fixtures, docs or prompts.
   Real values live in `.env` (gitignored); commit `.env.example` with `REPLACE_ME` placeholders.
2. **Never bypass hooks** with `git commit --no-verify`. If `gitleaks` fires, remove the secret and
   **rotate it**. CI runs the same scan and blocks the PR anyway.
3. **Branches are `<type>/<slug>`**, types `feat fix chore docs ci refactor test perf build style revert ai`.
   Work happens on a branch, never directly on `dev`, `next` or `main`.
4. **PR titles are Conventional Commits** (`feat(scope)!: summary`). The title becomes the squash commit
   and drives the SemVer bump: `!` / `BREAKING CHANGE` major, `feat` minor, everything else patch.
5. **Do not hand-edit** version numbers, `CHANGELOG.md` sections or tags: the release pipeline writes them.
6. **Change automation and docs together.** If you touch workflows, scripts, the makefile or conventions,
   update this file, `README.md`, `.github/copilot-instructions.md` and `.github/WORKFLOW.md` in the same PR.
7. **Keep it generic.** Do not bake a product, framework or package manager into template files that
   downstream repos inherit; put stack specifics behind `scripts/stack.sh` or a skill.
8. **No local agent state in git**: `.claude/`, `.agents/`, `.codex/`, `.worktrees/`, `.env`.

## Branches, PRs and releases

```
<type>/<slug> --PR (squash)--> dev --promote PR (merge)--> next --cut--> release/vX.Y.Z --draft PR (merge)--> main
```

- `dev` is the default branch. Drafts run only `guard`; **ready for review** starts `check`.
- A schedule (22:00 UTC) or the **Promote to next** workflow opens `dev -> next`. A push to `next` cuts
  `release/vX.Y.Z` (version files + `CHANGELOG.md`) and opens a draft PR into `main`.
- Merging that PR tags `vX.Y.Z`, publishes the GitHub Release, which triggers `publish.yml`.
- Required checks: `guard`, `check`, `Detect hardcoded secrets`.

If this file and the automation disagree, `.github/BRANCH-AND-RELEASE-POLICY.md` (rules),
`.github/LIFECYCLE.md` (stages) and `.github/WORKFLOW.md` (operations) win.

## Repository map

| Path                                                                | What it is                                                                                           |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `makefile`                                                          | The one entry point: every dev and CI step is a target                                               |
| `scripts/`                                                          | `stack.sh` runner, `version.sh`, `semver.sh`, `release.sh`, `secrets.sh`, ...                        |
| `tests/template/`                                                   | Tests for those scripts (`make selftest`)                                                            |
| `.github/workflows/`                                                | `pr`, `secret-scan`, `security`, `promote`, `next`, `pr-merged`, `release`, `publish`, `matrix`, ... |
| `.github/actions/setup/`                                            | Composite action: detect stacks, install only their toolchains                                       |
| `.github/rulesets/`, `settings.yml`                                 | Branch/tag protection and repo settings as code                                                      |
| `.github/skills/`                                                   | Agent skills (single source of truth)                                                                |
| `.github/ISSUE_TEMPLATE/`, `PULL_REQUEST_TEMPLATE.md`, `CODEOWNERS` | Collaboration templates                                                                              |
| `.devcontainer/`                                                    | Codespaces / dev container                                                                           |

## Skills (`.github/skills/`)

| Skill                                            | Use it when                                                 |
| ------------------------------------------------ | ----------------------------------------------------------- |
| `dev-cycle`                                      | Running the local setup / dev / test loop                   |
| `branch-and-release`                             | Branching, PR titles, checks, hotfixes, how releases happen |
| `secrets-hygiene`                                | Touching `.env`, tokens, CI secrets, or a hook fired        |
| `e2e-testing`                                    | Writing or debugging end-to-end tests                       |
| `stack-python`                                   | Python / uv work                                            |
| `stack-typescript-react`                         | TypeScript and React work                                   |
| `stack-expo`                                     | Expo / React Native work                                    |
| `stack-rust-gpui`                                | Rust and GPUI work                                          |
| `stack-swiftui`                                  | SwiftUI / Xcode work                                        |
| `agents-building`                                | Building agents: prompts, tools, skills, MCP, evals         |
| `agentic-workflows`, `agentic-workflow-designer` | Only if you adopt GitHub Agentic Workflows (`gh aw`)        |

`make agents-link` symlinks `.claude/skills` and `.agents/skills` to this directory; `make agents-check`
validates frontmatter (`name` equals the directory, single-line `description`) and that `CLAUDE.md` imports
this file.

## Customizing a generated repository

1. Fill `README.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `LICENSE`, `.github/CODEOWNERS`.
2. Run `.github/scripts/bootstrap-repo.sh`, then set `AUTOMATION_APP_ID` and `AUTOMATION_APP_PRIVATE_KEY`
   (see `.github/WORKFLOW.md`, "Secrets").
3. Run `make dependabot` once the first stack manifest exists.
4. Delete skills and `.env.example` sections for stacks you do not use.
5. Replace the "template" wording in this file with the real product description.
