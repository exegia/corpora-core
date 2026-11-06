---
name: e2e-testing
description: End-to-end test conventions per stack (pytest, Playwright, Maestro, cargo test --test e2e, XCUITest), CI triggers, flake handling and test data. Use when asked to add e2e or smoke tests, run make e2e, label a PR run-e2e, or debug flaky e2e.
---

# E2E testing

**When to use:** adding or fixing end-to-end/smoke tests, wondering why e2e ran (or did not) in CI, or taming flaky tests.

## Run it

```sh
make e2e    # runs e2e for every detected stack
```

If the stack has no e2e convention files, `make e2e` is a no-op. To use a custom command, set the task's `<TASK>_CMD` override (see `dev-cycle`).

## Conventions per stack

| Stack  | Where                                      | Runner                    |
| ------ | ------------------------------------------ | ------------------------- |
| python | `tests/e2e/`                               | pytest                    |
| node   | `test:e2e` script or `playwright.config.*` | Playwright or your script |
| expo   | `.maestro/` flows                          | Maestro                   |
| rust   | `tests/e2e.rs` or `tests/e2e/main.rs`      | `cargo test --test e2e`   |
| swift  | UI test target in `XCODE_UITEST_TARGET`    | xcodebuild                |

## When CI runs e2e

- PRs into `next` or `main`
- PRs labelled `run-e2e` (add it for risky changes into `dev`)
- Pushes to `next`
- Nightly schedule

Workflows: `.github/workflows/matrix.yml` and `pr.yml`. Unit tests (`make test`) run on every PR; keep them separate from e2e.

## First smoke test

Pick one critical user path (start app, load main screen, one core action) and assert one visible outcome.

- python: `tests/e2e/test_smoke.py` with `@pytest.mark.e2e`; call the CLI/API via subprocess or httpx.
- node: `test:e2e` -> `playwright test`; one spec that opens `/` and checks the heading.
- expo: `.maestro/smoke.yaml` that launches the app and asserts the home text.
- rust: `tests/e2e.rs` that spawns the binary and checks exit code and output.
- swift: one XCUITest that launches the app and checks a label.

## Flake handling

1. Reproduce 10 times locally before touching CI settings.
2. Replace sleeps with condition waits (Playwright auto-wait, Maestro `assertVisible`, pytest polling helper).
3. Make tests independent: own data, no ordering assumptions, unique names.
4. Allow at most 1 retry in CI as a diagnostic, not a fix. Open an issue for any test that needs it.
5. Quarantine with an explicit skip reason and an issue link; do not delete silently.
6. Upload traces/screenshots/videos as artifacts on failure.

## Test data and secrets

- Use seeded or generated data; never production data or real user accounts.
- Credentials come from env vars populated by CI secrets (`make secrets-push`); never from committed files.
- Use a dedicated test account or sandbox with minimal permissions.
- Do not log tokens or full request headers in traces.

## Pitfalls

- Tests relying on network access to third parties; stub or use a sandbox.
- Hard-coded ports; read them from env or pick free ports.
- Mixing e2e into `make test`, which slows every PR.
- Mobile/Swift e2e need emulators or a macOS runner; keep the suite small there.
