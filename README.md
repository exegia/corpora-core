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
