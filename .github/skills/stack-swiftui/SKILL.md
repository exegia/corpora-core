---
name: stack-swiftui
description: SwiftUI conventions - SwiftPM vs Xcode project, XCODE_SCHEME, XCODE_DESTINATION and XCODE_UITEST_TARGET env vars, swift-format or SwiftLint, previews, UI tests, macOS runner cost and signing secrets. Use for Package.swift, .xcodeproj, iOS or macOS app work and releases.
---

# SwiftUI

**When to use:** a repo with `Package.swift`, `.xcodeproj`, or `.xcworkspace`: building, testing, linting, UI testing, or releasing an Apple-platform app.

## Detection and commands

- `Package.swift` -> `swift build` / `swift test`.
- `.xcodeproj` or `.xcworkspace` -> `xcodebuild`, driven by env vars below.
- Swift tasks need a macOS runner. Set it via the `CI_RUNNERS` repo variable.

| Variable | Purpose | Example |
| --- | --- | --- |
| `XCODE_SCHEME` | scheme to build/test | `MyApp` |
| `XCODE_DESTINATION` | xcodebuild destination | `platform=iOS Simulator,name=iPhone 16` |
| `XCODE_UITEST_TARGET` | UI test target for `make e2e` | `MyAppUITests` |

```sh
XCODE_SCHEME=MyApp make build
XCODE_SCHEME=MyApp XCODE_DESTINATION="platform=iOS Simulator,name=iPhone 16" make test
XCODE_UITEST_TARGET=MyAppUITests make e2e
```

Pick a simulator name that exists on the runner's Xcode (`xcrun simctl list devices`). Any task can still be overridden with `<TASK>_CMD`.

## Layout choice

- Prefer SwiftPM for libraries and for app logic: put models and view models in a package target so `swift test` runs fast without a simulator.
- Keep the Xcode project thin: app entry point, assets, entitlements, UI test target.
- Commit `Package.resolved` for apps.

## Lint and format

- `swift format` (swift-format) for formatting; SwiftLint for rules. Commit `.swift-format` / `.swiftlint.yml`.
- Wire them into `make lint-check` (check only) and `make fmt` (apply), for example via `LINT_CMD`/`FMT_CMD` overrides if not auto-detected.

## SwiftUI practices

- Keep views small and driven by state; push logic into `@Observable` models or view models.
- Use `#Preview` for every non-trivial view, with sample data; previews must not hit network or real storage.
- Add `accessibilityIdentifier` to elements UI tests rely on.
- Test logic with Swift Testing or XCTest; reserve UI tests for a few critical flows.

## Versions

The release script bumps `MARKETING_VERSION` in the Xcode project (and `CHANGELOG.md`). Do not edit it by hand in feature PRs. Build number (`CURRENT_PROJECT_VERSION`) can be set in CI or by fastlane.

## Signing and secrets

- Never commit certificates, `.p12`, `.p8`, provisioning profiles, or `.env`.
- Use fastlane match (encrypted certs repo, passphrase in secrets) or an App Store Connect API key (key id, issuer id, key contents) stored as GitHub secrets via `make secrets-push`.
- CI builds for tests should use unsigned simulator builds (`CODE_SIGNING_ALLOWED=NO`).
- Wire distribution through `DEPLOY_COMMAND` rather than hardcoding it.

## Pitfalls

- macOS minutes cost several times Linux minutes; keep lint on cheap runners where possible and run UI tests only in e2e triggers.
- Missing `XCODE_SCHEME` with multiple schemes causes the wrong scheme or a failure.
- Simulator names drift across Xcode versions.
- Flaky UI tests from animations; disable them in test launch arguments.
