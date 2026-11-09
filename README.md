# corpora-core

Core services and crates to support the Corpora apps suite including conversion runners, text-fabric builder, model typings generations, data sources, AI skills and agentic workflows.

## Workspace Structure

```text
crates/
├── corpora-core/       # Core types and traits shared across the suite
├── (planned) corpora-convert/    # Conversion runners for various formats
├── (planned) corpora-fabric/     # Text-Fabric builder and utilities
├── (planned) corpora-typegen/    # Model typings generation
├── (planned) corpora-source/     # Data source abstractions
└── (planned) corpora-agent/      # AI skills and agentic workflow support
```

## Quick Start

```bash
make doctor     # check required tools
make setup      # install deps, hooks, .env
make ci         # run full CI locally
```

## Development

```bash
make fmt        # format all crates
make lint-check # clippy with strict lints
make test       # run all tests
make build      # build all crates
```

## Adding a New Crate

```bash
cargo new crates/corpora-mycrate --lib
```

Then add to the new crate's `Cargo.toml`:

```toml
[package]
name = "corpora-mycrate"
version.workspace = true
edition.workspace = true
# ... inherit other workspace fields

[lints]
workspace = true
```

## Publishing

Crates are published to crates.io on tagged releases. Set `PUBLISH_CRATES=true` in repository variables and add `CARGO_REGISTRY_TOKEN` to the `crates` environment.

With `PUBLISH_GITHUB_PACKAGES=true`, `packages.yml` additionally publishes the generated types on each release:

- **npm**: `@exegia/corpora-types` to GitHub Packages (`npm.pkg.github.com`), assembled from `generated/typescript/`
- **Cargo**: `.crate` files attached to the GitHub Release (GitHub Packages has no Cargo registry)
- **SwiftPM**: the root `Package.swift` exposes `CorporaTypes` from `generated/swift/`; consume it straight from git with `.package(url: "https://github.com/exegia/corpora-core.git", from: "X.Y.Z")`

## License

MIT OR Apache-2.0

## Text-Fabric expert agent

Invoke `$text-fabric-expert` for corpus inspection, validation, annotation, conversion
and analysis. See [setup, MCP integrations and capability limits](agent/text-fabric-expert/README.md).
The bundle reuses Context-Fabric/Agora and existing validators; it does not replace
the Rust runtime or claim universal lossless document conversion.

## TEI → Text-Fabric

The Rust core also exposes [shared structural and spelling diagnostics](crates/corpora-core/README.md#shared-structural-and-spelling-diagnostics).
Callers can check XML without Python and receive source-bound locations and candidate
edits through the same report type as spelling. API callers own repair execution and
revalidation; the Python converter retains acquisition, projection and schema checks.
Python quality and repair previews request structural diagnostics through the same
Rust JSON-lines bridge used for spelling.
TEI metadata dates and primary document identifiers also use native
[purpose-aware validation](crates/corpora-core/README.md#purpose-aware-tei-dates-and-identifiers),
preserving source locations and keeping identity mismatches blocked.

[The converter package](packages/tei-to-tf/README.md) accepts local TEI files or
GitHub/Hugging Face URLs, separates metadata and explicit TOCs from reading text,
and preserves source bytes, structure and annotation spans.

```sh
uv run --project packages/tei-to-tf tei-to-tf source.xml --output /new/output
make -C packages/tei-to-tf check build
```


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

### EPUB conversion and visual QA

`packages/epub-to-tf` validates local EPUBs with the Rust `corpora-epub-check`
binary and exports deterministic Text-Fabric. Build that binary with
`cargo build -p corpora-convert --bin corpora-epub-check`, then run the package
tests with `uv run --project packages/epub-to-tf pytest -q packages/epub-to-tf/tests`.
`packages/epub-to-tf/tools/qa_browser.py BUNDLE SITE` builds a dark-mode view
of semantic TF HTML alongside the archived XHTML. The package README documents
its supported input, asset, repair, and QA boundaries.

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
