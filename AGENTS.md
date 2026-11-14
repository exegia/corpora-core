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

Shared conversion/model contracts start in `crates/corpora-core/schema`. After any
shared contract change, run `make types` to regenerate Rust, TypeScript, Swift and
SQL together, then `make types-check`. Never hand-edit generated models or add a
parallel one-language shared contract. `make ci` runs the read-only freshness check
and `make agents-test` (offline Text-Fabric agent tests); both skip when the
corresponding generator/bundle is absent. Missing, changed and extra generated
files fail CI. Commit schema, outputs, converter tests and agent guidance together.
The conversion workflows also check freshness; package publishing is gated on it.

Override any task for any stack with `<TASK>_CMD` (`make test TEST_CMD="pytest -x"`); force the stack list
with `STACKS="python node"`. Monorepos: only root manifests are detected, so set the overrides.

## Stacks

| Stack            | Detected by                        | Lint / types                      | Tests / e2e                                                     |
| ---------------- | ---------------------------------- | --------------------------------- | --------------------------------------------------------------- |
| Python (uv)      | `pyproject.toml`                   | ruff, mypy / pyright / ty         | pytest; e2e in `tests/e2e/`, evals in `tests/evals/`            |
| TypeScript/React | `package.json` (+ `tsconfig.json`) | scripts `lint`, `typecheck`       | `test`; e2e: `test:e2e` or Playwright                           |
| Expo             | `expo` dependency                  | as above, `expo-doctor`           | e2e: Maestro flows in `.maestro/`                               |
| Rust             | `Cargo.toml`                       | `cargo fmt`, `clippy -D warnings` | `cargo test` / nextest; e2e: `tests/e2e.rs`                     |
| Rust + GPUI      | `Cargo.toml` (`gpui` dependency)   | as above                          | `#[gpui::test]` with `TestAppContext`                           |
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
- Promotion skips matching `dev` and `next` trees. The release job detects the stacks, packages
  Rust workspace crates when present, installs Node dependencies before Node packaging, and
  attaches assets before immutability locks the release.
- Required checks: `guard`, `check`, `Detect hardcoded secrets`.
- The PR and Matrix test jobs install Poppler and Tesseract before PDF crate tests.
- Workspace crates that depend on each other use one-line `path` entries with a `version` in the root
  `[workspace.dependencies]`; `scripts/version.sh set` keeps those versions equal to the workspace version,
  because `cargo package` rejects unversioned path dependencies. `scripts/changelog.sh tidy` repairs the
  changelog layout (one blank line before each section, none at the end).

If this file and the automation disagree, `.github/BRANCH-AND-RELEASE-POLICY.md` (rules),
`.github/LIFECYCLE.md` (stages) and `.github/WORKFLOW.md` (operations) win.

## Repository map

| Path                                                                | What it is                                                                                                       |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `makefile`                                                          | The one entry point: every dev and CI step is a target                                                           |
| `scripts/`                                                          | `stack.sh` runner, `version.sh`, `semver.sh`, `release.sh`, `secrets.sh`, ...                                    |
| `tests/template/`                                                   | Tests for those scripts (`make selftest`)                                                                        |
| `.github/workflows/`                                                | `pr`, `secret-scan`, `security`, `promote`, `next`, `pr-merged`, `release`, `publish`, `packages`, `matrix`, ... |
| `.github/actions/setup/`                                            | Composite action: detect stacks, install only their toolchains                                                   |
| `.github/rulesets/`, `settings.yml`                                 | Branch/tag protection and repo settings as code                                                                  |
| `.github/skills/`                                                   | Agent skills (single source of truth)                                                                            |
| `.github/ISSUE_TEMPLATE/`, `PULL_REQUEST_TEMPLATE.md`, `CODEOWNERS` | Collaboration templates                                                                                          |
| `.devcontainer/`                                                    | Codespaces / dev container                                                                                       |

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
| `stack-rust`                                     | Rust crate publishing to crates.io                          |
| `stack-rust-gpui`                                | Rust and GPUI desktop app work                              |
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

## PDF extraction benchmark

`crates/corpora-pdf/benchmarks/benchmark.py` compares source-pinned page regions
with independent image transcriptions through native extraction and raster OCR.
Run `python3 -m unittest discover -s crates/corpora-pdf/benchmarks -p 'test_*.py'`;
root stack detection does not run this Python suite. See the benchmark README for
the synthetic smoke command and local-only real-PDF manifest. Keep attachments,
transcriptions and generated reports out of Git; retain reference review status.
Use `--tessdata-dir` for isolated multilingual models; reports retain model hashes
and missing requested languages fail rather than silently falling back.
The PR test job installs Poppler, Tesseract and uv (for the review page's TEI column)
when the PDF crate is present, and runs the benchmark, PDF review-browser and OCR candidate Python suites after `make ci`.
The crate-owned skill is `crates/corpora-pdf/skills/pdf-ocr/SKILL.md`, discovered
through `.github/skills/pdf-ocr`. Its prompt and proposal are in the crate's
`agent/` directory. Exact missing marks require image-verified evidence; script
detection alone reports review risk with locations and unknown missing marks.

## EPUB conversion package

`packages/epub-to-tf` converts local EPUBs through the Rust `corpora-epub-check`
validator. Run `cargo build -p corpora-convert --bin corpora-epub-check` and
`uv run --project packages/epub-to-tf pytest -q packages/epub-to-tf/tests`.
`packages/epub-to-tf/tools/qa_browser.py BUNDLE SITE` generates a dark-mode
semantic TF view beside the original XHTML for visual QA. See the package README
for limits, repair policy, assets, and exact verification commands; root stack
detection does not discover this nested Python package.

`packages/tf-ai-resolver` runs the Text-Fabric expert on an exact, source-pinned
selection. Its loopback `serve` command connects the EPUB QA page to proposals;
explicit `apply` writes a derived `resolved_reading` feature while retaining
source slots. Run its Ruff, mypy, pytest, and build checks from that package.
`.github/workflows/epub-resolver.yml` runs both nested package suites on PRs.

## PDF conversion package

`packages/pdf-to-tf` converts a local PDF to TEI and then to TF through `tei-to-tf`.
It extracts with the Rust `corpora-pdf-extract` binary and converts only when the
conversion score is greater than 95%. It verifies every line, word and page through
the real loader, and writes `conversion-report.md` with located issues and suggested
fixes. Run `cargo build -p corpora-pdf --bin corpora-pdf-extract`, then
`make -C packages/pdf-to-tf check build`. `.github/workflows/pdf-converter.yml`
runs these on relevant PRs. The score is OCR evidence, not accuracy against a
reference. `tei-to-tf` gained opt-in `--milestones pages` and `--facsimile zones`
for this package; its defaults are unchanged.


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
Build with `npm run build --prefix packages/quality-ai` if install scripts are disabled.
Use `--ai-bridge packages/quality-ai/dist/bridge.js` with `AI_GATEWAY_API_KEY` in the
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

The PDF QA builder renders source pages to PNG at the extraction coordinate scale,
so the internal browser does not need a PDF plugin. Findings are collapsed by
default and script findings link to their extracted element. Original PDFs and
raw JSON remain available; the viewer never applies OCR candidates.
A third column renders the TEI that `pdf-to-tf` builds from the same extraction
as HTML, labelled by semantic type; `--no-tei` skips it (it needs `uv`).

The bounded PDF OCR candidate tool is `crates/corpora-pdf/tools/ocr_review.py`.
Run its credential-free tests with `python3 -m unittest discover -s crates/corpora-pdf/tools -p 'test_*.py'`.
It preserves source text and emits review-required candidates; hosted recognition
requires explicit provider selection and a request cap. Use `--provider vercel`
with `AI_GATEWAY_API_KEY` (preferred), or `--provider mistral` with `MISTRAL_API_KEY`.
Gateway requests preserve reported token usage, exclude reference text and have no
client retries; cached candidates remain subject to image review. The first cache
miss checks authenticated model eligibility before inference. Use `--gateway-model`
for explicit model selection; the tool respects existing team provider allowlists.
Direct Mistral OCR also retains validated `usage_info` page/byte counters and
the reported OCR model in successful caches and rejected-response reports.
Missing usage stays unknown; cached counters describe the original request.
Rejected JSON responses retain sanitized finish reasons and token usage when supplied,
including reasoning-token counts; partial text is rejected and is never cached as a candidate.
`--gateway-reasoning-effort low|high` explicitly selects a catalog-supported effort
for Vercel and separates its cache; omitting it preserves the existing request defaults.
`--gateway-max-tokens N` (1–32768, default 1024) sets the Vercel output cap; a non-default
cap must fit the catalog's advertised model limit and uses a separate cache.
