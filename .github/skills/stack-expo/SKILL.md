---
name: stack-expo
description: Expo and React Native conventions - expo install, expo-doctor, EAS build and update with EXPO_TOKEN, app.json version sync, Maestro flows, expo export packaging, and files never to commit. Use for app.json, eas.json, mobile builds, or Maestro e2e work.
---

# Expo (React Native)

**When to use:** a repo whose `package.json` depends on `expo`: adding native-compatible packages, building with EAS, writing Maestro flows, or releasing a mobile app.

## Commands

The `node` stack runs package.json scripts (flavor `expo` detected from deps). Typical scripts:

```json
{
  "scripts": {
    "dev": "expo start",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "test": "jest",
    "build": "expo export"
  }
}
```

```sh
npx expo install react-native-reanimated   # picks the SDK-compatible version
npx expo-doctor                            # checks deps and config
npx expo install --check                   # list mismatched versions
```

Use `expo install`, not `npm install`, for packages that have native code.

## Version sync

The release script rewrites `expo.version` in `app.json` (and `package.json` `version`). Do not edit them manually in feature PRs. Native build numbers (`ios.buildNumber`, `android.versionCode`) are best handled by EAS with `"autoIncrement": true` in `eas.json` or `appVersionSource: "remote"`.

## EAS

```sh
npx eas-cli build --platform all --profile preview
npx eas-cli update --branch preview --message "fix: crash on launch"
```

- Authenticate in CI with the `EXPO_TOKEN` secret (set via `make secrets-push`); never commit it.
- Keep profiles in `eas.json` (`development`, `preview`, `production`).
- Use `PREVIEW_DEPLOY_COMMAND` and `DEPLOY_COMMAND` repo variables to hook EAS commands into preview/release deploys.
- OTA updates only change JS/assets; native changes need a new build.

## Packaging

`make pack` should run `expo export` (output goes to `dist/` by default). Override with `PACK_CMD` if you use another output dir.

## E2E with Maestro

Flows live in `.maestro/*.yaml`. Minimal smoke flow:

```yaml
appId: com.example.app
---
- launchApp
- assertVisible: "Welcome"
```

Run locally with `maestro test .maestro/` against a simulator or dev build. See `e2e-testing` for CI triggers.

## Never commit

- `google-services.json`, `GoogleService-Info.plist`
- keystores (`*.jks`, `*.keystore`), `*.p12`, provisioning profiles, `*.p8`
- `.env` (commit `.env.example`); only `EXPO_PUBLIC_*` values are bundled into the app and are public by design, so never put secrets there
- store EAS credentials with `eas credentials` or as CI secrets

## Pitfalls

- Mismatched SDK dependency versions cause obscure native crashes; run `expo-doctor`.
- Editing `ios/` or `android/` in a managed project; use config plugins or `expo prebuild` deliberately.
- Secrets in `app.json` `extra`; it ships in the bundle.
- Long EAS builds in PR CI; keep them to labelled or release workflows.
