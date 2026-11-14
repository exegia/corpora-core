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
- **Crate dependencies:** workspace crates depend on each other through versioned `path` entries in the
  root `[workspace.dependencies]`; `scripts/version.sh set` bumps them with the workspace version.
- **Workflows:** `.github/workflows/*.yml` are plain workflows; steps call `make` targets. Pin third-party
  actions to a commit SHA with a version comment. Keep jobs least-privilege.
- **Release assets:** package crates before `tag-release`; it attaches them during release creation.
  Skip promotion when `dev` and `next` have the same tree.
- **Docs move with automation:** update `AGENTS.md`, `README.md`, and `.github/WORKFLOW.md` in the same PR.
- **Template stays generic:** stack specifics go behind `scripts/stack.sh` or `.github/skills/`.
- **Skills:** `.github/skills/<name>/SKILL.md`, frontmatter `name` equal to the directory and a one-line
  `description`. `make agents-check` enforces it.

## Shared models and agent checks

Shared conversion/model contracts start in `crates/corpora-core/schema`. Run
`make types` then `make types-check` to regenerate/check Rust, TypeScript, Swift
and SQL together; never hand-edit outputs or create parallel shared models.
`make ci` includes read-only `types-check` and offline `agents-test`; these skip
when their component is absent. Conversion workflows and package publishing check
generated freshness too. Commit schema, outputs, tests and agent guidance together.

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
The Matrix test job also installs Poppler and Tesseract before `make ci`.
The crate-owned skill is `crates/corpora-pdf/skills/pdf-ocr/SKILL.md`, discovered
through `.github/skills/pdf-ocr`. Its prompt and proposal are in the crate's
`agent/` directory. Exact missing marks require image-verified evidence; script
detection alone reports review risk with locations and unknown missing marks.

## EPUB conversion package

`packages/epub-to-tf` uses the Rust `corpora-epub-check` validator. Build with
`cargo build -p corpora-convert --bin corpora-epub-check` and verify with
`uv run --project packages/epub-to-tf pytest -q packages/epub-to-tf/tests`.
For visual QA, run `packages/epub-to-tf/tools/qa_browser.py BUNDLE SITE` to
compare semantic TF HTML with archived XHTML. The package README specifies
supported input, repair, and asset boundaries.

`packages/tf-ai-resolver` serves the QA site on loopback for exact TF text
selection, expert proposals, and explicit application to a derived reading
feature. The original slots stay intact. Run its locked Ruff, mypy, pytest,
and build checks from the package directory; see its README.
`.github/workflows/epub-resolver.yml` runs both nested suites on PRs.

`packages/pdf-to-tf` converts a local PDF to TEI and then TF only when the
conversion score is greater than 95%, verifies every line, word and page, and
reports located issues with suggested fixes. Build `corpora-pdf-extract`
(`cargo build -p corpora-pdf --bin corpora-pdf-extract`), then run
`make -C packages/pdf-to-tf check build`. `.github/workflows/pdf-converter.yml`
runs both on PRs. `tei-to-tf` gained opt-in `--milestones pages` and
`--facsimile zones`; its defaults are unchanged.


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
