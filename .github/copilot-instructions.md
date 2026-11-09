# Copilot instructions

Full rules are in [`AGENTS.md`](../AGENTS.md); this is the short form. This repository is a **generic
template** for Rust + GPUI, Python, TypeScript, React, Expo, SwiftUI and AI-agent projects.

## Commands (run from the repository root)

| Task                           | Command                                                        |
| ------------------------------ | -------------------------------------------------------------- |
| Check tools / first-time setup | `make doctor` / `make setup`                                   |
| Format and autofix             | `make fmt`                                                     |
| Lint, types, tests, build      | `make lint-check`, `make typecheck`, `make test`, `make build` |
| End-to-end tests               | `make e2e`                                                     |
| Everything CI runs on a PR     | `make ci`                                                      |
| Test the repo's own automation | `make selftest`                                                |
| Validate skills / instructions | `make agents-check`                                            |
| Scan for secrets               | `make secrets-scan`                                            |

Targets detect the stack from `pyproject.toml`, `package.json`, `Cargo.toml` or `Package.swift` /
`.xcodeproj` (`scripts/stack.sh`). Override any task with `<TASK>_CMD`, e.g. `make test TEST_CMD="..."`.
`copilot-setup-steps.yml` prepares the same toolchains for the coding agent.

## Conventions

- **Branches:** `<type>/<slug>` with type `feat|fix|chore|docs|ci|refactor|test|perf|build|style|revert|ai`,
  opened as PRs into `dev` (the default branch). Promotion: `dev` -> `next` -> `release/vX.Y.Z` -> `main`.
- **PR titles:** Conventional Commits, `feat(scope)!: summary`. They set the SemVer bump (`!` major,
  `feat` minor, else patch). Do not edit versions, tags or `CHANGELOG.md` by hand.
- **Workflows:** `.github/workflows/*.yml` are plain workflows; steps call `make` targets. Pin third-party
  actions to a commit SHA with a version comment. Keep jobs least-privilege.
- **Docs move with automation:** update `AGENTS.md`, `README.md`, and `.github/WORKFLOW.md` in the same PR.
- **Template stays generic:** stack specifics go behind `scripts/stack.sh` or `.github/skills/`.
- **Skills:** `.github/skills/<name>/SKILL.md`, frontmatter `name` equal to the directory and a one-line
  `description`. `make agents-check` enforces it.

## Secrets

- Never commit credentials, tokens or keys, including in tests, fixtures, docs and examples.
- Real values belong in `.env` (gitignored); commit `.env.example` with `REPLACE_ME` placeholders.
- `gitleaks` runs as a pre-commit hook and as the required `Secret Scan` workflow. Never use
  `--no-verify`; if it fires, remove the secret and rotate it.
- Do not commit `.claude/`, `.agents/`, `.codex/`, `.worktrees/` or workflow logs.

## Domain agent bundles

Text-Fabric work uses `.github/skills/text-fabric-expert/SKILL.md` and
`agent/text-fabric-expert/SYSTEM.md`. Its source map, MCP configuration generator
and verification instructions live in `agent/text-fabric-expert/README.md`.

## TEI conversion package

`packages/tei-to-tf` provides the TEI acquisition/conversion CLI. Run
`make -C packages/tei-to-tf check build` for its locked Python lint, type, test
and package checks; root stack detection does not discover nested Python projects.
`.github/workflows/tei-converter.yml` runs these checks on relevant PR changes.
See the package README for reading policies, metadata separation and supported boundaries.

## EPUB conversion package

`packages/epub-to-tf` uses the Rust `corpora-epub-check` validator. Build with
`cargo build -p corpora-convert --bin corpora-epub-check` and verify with
`uv run --project packages/epub-to-tf pytest -q packages/epub-to-tf/tests`.
For visual QA, run `packages/epub-to-tf/tools/qa_browser.py BUNDLE SITE` to
compare semantic TF HTML with archived XHTML. The package README specifies
supported input, repair, and asset boundaries.


### Language and spelling QA

`crates/corpora-core` provides language/dictionary selection and the optional
Matchum-backed `spellcheck` feature (Rust 1.91). Build `corpora-text-check` and install
pinned dictionary data with `crates/corpora-core/tools/install_dictionaries.py`.
The TEI converter's `--quality-engine` / `--dictionaries` options run audited
validate, repair, and revalidate passes, preserving originals and blocking unresolved
errors. Corpus wording is never automatically changed. The TEI workflow builds the
Rust bridge, installs pinned `en_US` and `fr_FR` dictionaries, and runs the real
dictionary integration tests, including English metadata under a French corpus policy.
See the core and converter READMEs for the policy, setup, and diagnostic contracts.

Hosted quality review is optional via `packages/quality-ai` (Vercel AI SDK, Node 22+).
Run `npm ci --prefix packages/quality-ai`, `npm run check --prefix packages/quality-ai`
and `npm test --prefix packages/quality-ai`; CI runs these without hosted credentials.
Use `--ai-bridge packages/quality-ai/bridge.mjs` with `AI_GATEWAY_API_KEY` in the
process environment. Never put credentials in reports or browser assets. See
`packages/quality-ai/README.md` for model selection, request budgets and limitations.

### ShellCheck hook installation

The ShellCheck pre-commit hook installs pinned `shellcheck-py==0.11.0.1` from
PyPI, using its prebuilt wheel on supported platforms instead of rebuilding the
Git checkout and downloading a binary from GitHub. The hook still checks shell
scripts with `-S warning -x`; CI runs it as part of `hygiene`.
The secret-scan workflow retries the pinned gitleaks release download, then builds
the same pinned version through the Go module proxy if the release CDN is unavailable.
Both installation paths run the same required, redacted scan.
