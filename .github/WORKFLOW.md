# Operating the pipeline

PDF extraction has an additional local benchmark suite outside root stack
detection: `python3 -m unittest discover -s crates/corpora-pdf/benchmarks -p 'test_*.py'`.
See `crates/corpora-pdf/benchmarks/README.md` for the synthetic end-to-end command.
Private PDF manifests and results remain outside Git; no hosted service is used.
The benchmark accepts `--tessdata-dir` for isolated language models and records
their hashes. Missing or unloadable requested languages cannot silently fall back.
When the PDF crate is present, the PR test job installs Poppler, Tesseract and uv
(the review page renders its TEI column through pdf-to-tf) before `make ci`, then runs the benchmark, PDF review-browser and OCR candidate Python suites.
The Matrix test job installs Poppler and Tesseract before `make ci` as well.
PDF OCR guidance is owned by `crates/corpora-pdf/skills/pdf-ocr` and linked into
`.github/skills/pdf-ocr`; its prompt/proposal are under `crates/corpora-pdf/agent`.

How to set up a repository generated from this template and run the release flow. Rules live in
[`BRANCH-AND-RELEASE-POLICY.md`](./BRANCH-AND-RELEASE-POLICY.md), stages in [`LIFECYCLE.md`](./LIFECYCLE.md).

## 1. Bootstrap a new repository

1. Create the repo from the template (`Use this template`). Push `main`.
2. Locally: `make doctor`, then `make setup`.
3. Create the **automation GitHub App** (see Secrets) and install it on the repo.
4. Apply settings, labels and rulesets in one go:

   ```bash
   export BYPASS_ACTORS_JSON='[{"actor_id":<APP_ID>,"actor_type":"Integration","bypass_mode":"always"}]'
   .github/scripts/bootstrap-repo.sh          # or: make repo-bootstrap
   ```

   It creates `dev` and `next` from `main`, makes `dev` the default branch, applies `.github/settings.yml`
   (squash/merge options, auto-merge, delete-branch-on-merge), switches on Dependabot alerts and security
   updates, secret scanning with push protection, and private vulnerability reporting, creates the labels, and
   applies `.github/rulesets/*.json`. `DRY_RUN=1` previews. Re-running is safe.

5. Set the secrets and variables below, then `make secrets-doctor`.
6. `make dependabot` once the first stack manifest exists, then replace the `REPLACE_ME` values in
   `SECURITY.md`, `CODE_OF_CONDUCT.md`, `LICENSE` and `.github/CODEOWNERS`.

Rulesets are inert until applied. `make rulesets-diff` shows what GitHub has; `make rulesets-apply` pushes the
files, matching by `name` (keep names, or a second ruleset is created). Apply them **after** the first release
lands if you want to seed `main` directly.

## 2. Secrets and variables

Secrets (repository level unless an environment is named):

| Name                                              | Needed for                                          |
| ------------------------------------------------- | --------------------------------------------------- |
| `AUTOMATION_APP_ID`, `AUTOMATION_APP_PRIVATE_KEY` | **Required.** Opens PRs, cuts branches, pushes tags |
| `CLAUDE_CODE_OAUTH_TOKEN`                         | Optional AI review job                              |
| `NPM_TOKEN` (env `npm`)                           | `PUBLISH_NPM`                                       |
| `CARGO_REGISTRY_TOKEN` (env `crates`)             | `PUBLISH_CRATES`                                    |
| `EXPO_TOKEN` (env `eas`)                          | `EAS_BUILD_PROFILE`                                 |
| provider tokens (env `preview` / `production`)    | `PREVIEW_DEPLOY_COMMAND` / `DEPLOY_COMMAND`         |

PyPI uses trusted publishing (OIDC): register the repo and the `pypi` environment on pypi.org, no secret.

The GitHub App needs **Contents: write**, **Pull requests: write**, **Workflows: write** and **Metadata: read**.
The App must be the actor that creates tags: tags pushed with `GITHUB_TOKEN` do not start `publish.yml`, and PRs
opened with it never get their required checks.

Variables:

| Name                                                       | Effect                                                                                        |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `CI_RUNNERS`                                               | JSON array of runner labels for PR checks (default from stack detection)                      |
| `MATRIX_RUNNERS`                                           | Runners for `matrix.yml` (default ubuntu + macOS)                                             |
| `XCODE_SCHEME`, `XCODE_DESTINATION`, `XCODE_UITEST_TARGET` | Swift/Xcode builds, tests and UI tests                                                        |
| `VERSION_CMD`                                              | Replaces `scripts/version.sh set` at release cut (monorepos)                                  |
| `PUBLISH_PYPI`, `PUBLISH_NPM`, `PUBLISH_CRATES`            | `true` enables that publish job                                                               |
| `PUBLISH_GITHUB_PACKAGES`                                  | `true` enables `packages.yml`: npm to GitHub Packages, `.crate` release assets, SwiftPM check |
| `EAS_BUILD_PROFILE`                                        | Queues an EAS build for that profile                                                          |
| `PREVIEW_DEPLOY_COMMAND`, `DEPLOY_COMMAND`                 | Shell run after `next` pushes / production tags                                               |
| `DEPENDENCY_REVIEW`, `CODEQL`                              | `false` switches that security job off                                                        |

Locally: `make env-init` creates `.env` (mode 600) from `.env.example`; `make env-check` diffs keys;
`make secrets-push [ENV_FILE=.env.ci] [ENVIRONMENT=npm]` and `make secrets-vars-push` load dotenv files into
GitHub (names are listed for confirmation, values never printed); `make secrets-list` shows names only.

## 3. Day to day

```bash
git switch -c feat/123-add-parser dev      # branch off dev
make fmt && make ci                        # same thing CI runs
gh pr create --draft --base dev --title "feat: add parser"
gh pr ready                                # starts hygiene, test, check
```

Squash-merge into `dev`. Everything after that is automatic until the release PR: review the draft PR into
`main`, mark it ready, merge it with a merge commit.

### Shared model and conversion gates

For new or changed shared conversion/model contracts, edit
`crates/corpora-core/schema`, run `make types` then `make types-check`, and commit
Rust, TypeScript, Swift and SQL outputs together. `make ci` runs read-only
`types-check` and offline `agents-test`, so required PR checks reject model drift
and agent contract/config regressions. These targets skip absent components in
template-derived repositories. The three conversion workflows also run
`types-check` and trigger on schema/generator, generated output and Text-Fabric
agent/skill changes. `packages.yml` gates every publishing job on generated
freshness before copying TypeScript files or checking SwiftPM.

`quality-ai` compiles automatically on `npm ci`/`npm install` through `prepare`;
its tests rebuild too. The TEI workflow installs and compiles it before converter
checks. Rebuild explicitly after source edits or with disabled lifecycle scripts.
Agent unit tests do not establish per-corpus fidelity or live model quality.

`packages/corpus-validate` has a separate PR workflow because root stack
detection skips nested Python packages. It runs real Text-Fabric and
Context-Fabric loader tests, including a `.cfm` mmap reload, followed by a
wheel build. The hosted API stages bounded uploads and invokes its CLI; legacy
server paths and conversion job IDs are not accepted as upload targets.

## 4. Manual operations

```bash
make bump-info                  # latest tag, implied bump, next version
make next-version BUMP=minor    # what the next tag would be called
make changelog VERSION=1.2.0    # preview the CHANGELOG section
make bootstrap-lanes            # create origin/dev and origin/next if missing
make promote-pr VERSION=1.2.0 BUMP=minor
make cut-release VERSION=1.2.0  # normally run by next.yml
make cleanup-local              # prune local branches whose remote is gone
```

`promote-pr` skips matching `dev` and `next` trees. The release job uses `scripts/stack.sh list`:
Rust workspaces package `.crate` files, Node stacks install dependencies before `make pack`, Python
stacks run `make pack`, and other stacks
continue without binary assets. `make tag-release` attaches available files while creating the
immutable GitHub Release.
An already published release is skipped; a draft is retried by uploading assets and publishing it.
Everything is parameterized on `TRUNK` (default `main`).

## 5. Troubleshooting

| Symptom                                     | Cause and fix                                                                                             |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `guard` fails on the title                  | Use `<type>(scope)!: summary`; edit the PR title, it re-runs on `edited`                                  |
| Required `check` never appears              | PR is still a draft, or it was opened with `GITHUB_TOKEN` instead of the App                              |
| `promote` / `next` fail at their first step | `AUTOMATION_APP_ID` / `AUTOMATION_APP_PRIVATE_KEY` missing: `make secrets-doctor`                         |
| Tag exists but `publish.yml` did not run    | The tag was pushed with `GITHUB_TOKEN`; create it as the App                                              |
| Scheduled workflows not firing              | They run from the default branch; make sure `dev` has the files                                           |
| `guard` says manifests disagree             | `scripts/version.sh check` lists them; delete the stale `VERSION` file once a real manifest has a version |
| Publish: path dependency has no version     | Move it to a one-line `path` + `version` entry in root `[workspace.dependencies]`; `version.sh set` bumps it |
| `hygiene` fails on `CHANGELOG.md` layout    | Run `scripts/changelog.sh tidy`; releases cut after the layout fix already write it correctly            |
| Cut-release cannot push workflow changes    | Grant the App **Workflows: write**                                                                        |
| Hook fired on a secret                      | Remove it, rotate it, never `--no-verify`; see `skills/secrets-hygiene`                                   |

## 6. Template maintenance

`make selftest` runs `tests/template/` (stack detection, SemVer, versions, PR guard, secrets, changelog, agent
assets). Keep it green when you change `scripts/`. Lint workflows with `actionlint` and scripts with
`shellcheck -S warning -x scripts/*.sh .github/scripts/*.sh` (both also run as pre-commit hooks).

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

## EPUB conversion verification

For `packages/epub-to-tf`, build `corpora-epub-check` with
`cargo build -p corpora-convert --bin corpora-epub-check`, then run
`uv run --project packages/epub-to-tf pytest -q packages/epub-to-tf/tests`.
Use `packages/epub-to-tf/tools/qa_browser.py BUNDLE SITE` to compare semantic
TF HTML with the original archived XHTML in a dark-mode local QA site. The
package README covers conversion, repair and asset limits; root `make ci` does
not discover the nested Python package.

For the QA selection resolver, run `uv run --group dev ruff check .`,
`uv run --group dev mypy src`, `uv run --group dev pytest -q`, and `uv build`
from `packages/tf-ai-resolver`. Its loopback `serve` command connects semantic
TF HTML selection to the expert; `apply` creates a reviewed derived reading
feature without changing original slots. See the resolver README.
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
