---
name: stack-rust-gpui
description: Rust and GPUI desktop app conventions - workspace layout, cargo fmt and clippy -D warnings, gpui::test with TestAppContext, cheap render, notify discipline, CI libs, macOS runner, bundling. Use for Cargo.toml, GPUI views, clippy or release packaging work.
---

# Rust + GPUI

**When to use:** editing a Cargo project at the repo root, writing GPUI views/entities/tests, fixing clippy or CI failures for Rust, or packaging a desktop app.

## What CI runs

Detected by `Cargo.toml` at the root; flavor `gpui` when the `gpui` crate is a dependency.

```sh
make fmt          # cargo fmt (apply)
make lint-check   # cargo fmt --check + cargo clippy -D warnings
make test         # cargo test (or nextest if installed)
make build        # cargo build
make e2e          # cargo test --test e2e
make pack         # artifacts into dist/
```

Warnings are errors. Fix clippy findings; use a narrow `#[allow(...)]` with a reason only when unavoidable.

## Layout

- Single crate: `src/main.rs` + `src/lib.rs` (keep logic in the lib so it is testable).
- Workspace: root `Cargo.toml` with `[workspace] members = ["crates/*"]`. Put shared deps in `[workspace.dependencies]`.
- Detection reads the root manifest only; for nested crates use a root workspace.
- Commit `Cargo.lock` for apps and binaries.
- Separate state/model code from views so most tests need no window.

## GPUI practices

- Keep `render` cheap and pure: no I/O, no allocation-heavy work, no spawning. Compute in the model and cache.
- State lives in entities (`Entity<T>`); call `cx.notify()` only when observable state actually changed, and never from `render`.
- Avoid notify loops: observer A notifying B notifying A.
- Store `Subscription` and `Task` handles in the struct; dropping them cancels work.
- Use `cx.spawn` for async and `WeakEntity` in long-lived closures to avoid leaks.

## Tests

```rust
#[gpui::test]
async fn increments(cx: &mut gpui::TestAppContext) {
    let model = cx.new(|_| Counter { n: 0 });
    model.update(cx, |m, cx| { m.n += 1; cx.notify(); });
    cx.run_until_parked();
    assert_eq!(model.read_with(cx, |m, _| m.n), 1);
}
```

Check the exact API against the pinned gpui version before copying. Use `cx.run_until_parked()` instead of sleeps. Plain logic gets plain `#[test]`.

## CI and runners

- Linux runners need system libs for GPUI (X11/Wayland, xkbcommon, fontconfig, vulkan, alsa as applicable). Install them in a setup step or via `copilot-setup-steps.yml`; `make doctor` reports missing tools only.
- Metal builds and macOS bundles need a macOS runner. Set via `CI_RUNNERS`; macOS minutes cost more, so keep Linux for lint/tests where possible.

## Release bundling

`make pack` uses the stack default; for desktop bundles set `PACK_CMD`, for example `PACK_CMD="cargo bundle --release"` (requires `cargo install cargo-bundle`). The release script bumps `Cargo.toml` version; do not edit by hand.

## Pitfalls

- Unpinned git dependency on gpui breaks reproducibility; pin a `rev` and keep `Cargo.lock`.
- `#[gpui::test]` code run under plain `#[test]` panics; do not mix.
- Heavy work inside `render` makes frames janky.
- Forgetting `cx.notify()` leaves the UI stale; calling it constantly burns CPU.
