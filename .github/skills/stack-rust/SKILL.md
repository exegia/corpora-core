---
name: stack-rust
description: Rust crate conventions for library and CLI publishing to crates.io - workspace-level lints, thiserror, doc comments, cargo publish, CI and release workflow. Use when editing Cargo.toml, fixing clippy, writing Rust code, or publishing to crates.io.
---

# Rust Crate Publishing

**When to use:** editing Rust code at the repo root, configuring Cargo.toml for publishing, fixing clippy or CI failures, or preparing a release to crates.io.

## What CI runs

Detected by `Cargo.toml` at the root.

```sh
make fmt          # cargo fmt (apply)
make lint-check   # cargo fmt --check + cargo clippy -D warnings
make typecheck    # (skipped - covered by clippy)
make test         # cargo test (or nextest if installed)
make build        # cargo build --workspace --all-targets
make pack         # cargo build --release
```

Warnings are errors. Fix clippy findings; use `#[expect(clippy::lint_name)]` with a justification comment when suppression is unavoidable.

## Layout

Single publishable crate at the root:

```
Cargo.toml          # [package] + [lints]
Cargo.lock          # commit for apps/CLIs; optional for pure libs
rust-toolchain.toml # pin the toolchain for reproducibility
rustfmt.toml        # formatting config
src/
  lib.rs            # public API + doc comments
  main.rs           # CLI (optional, behind a feature)
  error.rs          # Error type with thiserror
tests/
  integration.rs    # integration tests
```

## Cargo.toml essentials for publishing

```toml
[package]
name = "crate-name"
version = "0.0.0"           # release workflow sets this
edition = "2024"
rust-version = "1.85"
authors = ["Team <team@example.com>"]
description = "Short description"
documentation = "https://docs.rs/crate-name"
readme = "README.md"
homepage = "https://github.com/org/repo"
repository = "https://github.com/org/repo"
license = "MIT OR Apache-2.0"
keywords = ["keyword1", "keyword2"]
categories = ["category"]
include = ["src/**/*", "Cargo.toml", "README.md", "LICENSE"]

[lints.rust]
missing_docs = "warn"
unsafe_code = "deny"
unused_must_use = "deny"

[lints.clippy]
all = { level = "warn", priority = -1 }
pedantic = { level = "warn", priority = -1 }
nursery = { level = "warn", priority = -1 }
cargo = { level = "warn", priority = -1 }
```

## Coding practices

### Error handling

- Use `thiserror` for library errors (derive `Error` with `#[error("...")]` messages).
- Use `anyhow` only in binaries, never in library code.
- Return `Result<T, E>` for fallible operations; never panic in production code.
- Use `?` over match chains; avoid `.unwrap()` / `.expect()` outside tests.

### Ownership

- Prefer `&str` over `String`, `&[T]` over `Vec<T>` in function parameters.
- Clone only when you need ownership; avoid cloning in loops.
- Use `Cow<'_, T>` when you might or might not need ownership.

### Documentation

- Every public item gets a `///` doc comment explaining *what* and *how*.
- Use `//` comments to explain *why* (safety invariants, workarounds, design rationale).
- Doc-tests (`///`) count as tests; keep examples simple and correct.
- Every `TODO` links an issue: `// TODO(#42): ...`

### Testing

- Name tests descriptively: `parse_should_return_error_when_input_empty()`.
- One assertion per test when possible.
- Use `insta` for snapshot testing generated output.
- Integration tests go in `tests/`; unit tests inline with `#[cfg(test)]`.

## Publishing workflow

1. **Set up crates.io auth:** `cargo login` locally; set `CARGO_REGISTRY_TOKEN` in the `crates` environment on GitHub.
2. **Enable publishing:** set repository variable `PUBLISH_CRATES=true`.
3. **Release cycle:** PRs merge to `dev` → promote to `next` → release branch bumps version → merge to `main` → tag triggers `publish.yml` → `cargo publish --locked`.
4. **Dry run:** `cargo package --workspace --locked` (what the release `crate-assets` job runs) or
   `cargo publish --dry-run` before the release.
5. **Crates that depend on each other:** declare them once in the root `[workspace.dependencies]` as
   one-line entries with both `path` and `version` (`demo-core = { path = "crates/demo-core", version = "0.1.0" }`)
   and use `demo-core = { workspace = true }` in members. `scripts/version.sh set` keeps the version equal to
   the workspace version; a path dependency without one fails `cargo package`.

The release workflow handles version bumps; never edit `Cargo.toml` version by hand.

## CI notes

- `cargo fmt --all -- --check` and `cargo clippy --workspace --all-targets --all-features --locked -- -D warnings` run on every PR.
- Tests run with `cargo test` or `cargo nextest run` if nextest is available.
- Cache is handled by `Swatinem/rust-cache@v2`.

## Pitfalls

- Missing `edition`, `license`, or `description` blocks publishing.
- Forgetting `--locked` in CI causes builds to drift from the lockfile.
- `missing_docs` lint catches undocumented public items; add docs or mark items `pub(crate)`.
- Large dependencies slow CI; consider feature flags to make heavy deps optional.
