---
name: stack-typescript-react
description: TypeScript and React conventions - strict tsconfig, package manager detection from lockfile, the package.json scripts contract, Vitest and Testing Library, Playwright e2e, accessibility, npm provenance publishing. Use for package.json, tsconfig, React component or npm release work.
---

# TypeScript + React

**When to use:** repos with a root `package.json`: adding scripts or deps, writing components and tests, fixing lint/type failures, or publishing to npm.

## Package manager

Detected from the lockfile: `bun.lock`/`bun.lockb` -> bun, `pnpm-lock.yaml` -> pnpm, `yarn.lock` -> yarn, `package-lock.json` -> npm. Commit exactly one lockfile and use that manager everywhere. Flavors typescript/react are detected from dependencies.

## Scripts contract

The template runs these package.json scripts if present; missing ones are skipped:

| Script | Make target |
| --- | --- |
| `lint` | `make lint-check` |
| `typecheck` | `make typecheck` |
| `test` | `make test` |
| `test:e2e` | `make e2e` |
| `build` | `make build` |
| `dev` | `make dev` |
| `eval` | `make eval` |

Example:

```json
{
  "scripts": {
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:e2e": "playwright test",
    "build": "vite build",
    "dev": "vite"
  }
}
```

`lint` must not modify files (CI uses it as a check). `make fmt` applies autofix, so wire your formatter there or set `FMT_CMD`.

## TypeScript

- `tsconfig.json`: `"strict": true`, plus `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes` for new projects.
- No `any` without a comment; prefer `unknown` plus narrowing.
- Validate external data (API, env, JSON) at the boundary with a schema library.
- Use `import type` for type-only imports.

## React testing

- Vitest + `@testing-library/react` + `@testing-library/user-event`.
- Query by role and label, not test ids or class names.
- Test behavior (what the user sees), not implementation or hook internals.
- Mock the network at the boundary (for example MSW), not individual modules.

## Playwright e2e

Keep config in `playwright.config.ts`; start the app via `webServer`. See `e2e-testing` for CI triggers and flake handling.

## Accessibility

- Semantic elements first; ARIA only when needed.
- Every interactive control is keyboard reachable with a visible focus style.
- Images have alt text, inputs have labels.
- Add `eslint-plugin-jsx-a11y` and, optionally, axe checks in Playwright.

## Publishing

Set repo variable `PUBLISH_NPM` to `true` to publish on release. Use npm provenance (`npm publish --provenance --access public` from CI with `id-token: write`). The release script bumps `version` in `package.json`; set `"files"` or `.npmignore` and check with `npm pack --dry-run`. Store `NPM_TOKEN` (if used) as a GitHub secret only.

## Pitfalls

- Mixing package managers produces conflicting lockfiles and wrong detection.
- A `test` script that starts a watcher hangs CI; use `vitest run`.
- `lint` that autofixes hides problems in CI.
- Monorepo packages are not detected; use root scripts or `<TASK>_CMD` (see `dev-cycle`).
