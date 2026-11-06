# Branch & Release Policy

The rules: which branches exist, what may target what, how versions are chosen, and what is protected.
[`LIFECYCLE.md`](./LIFECYCLE.md) lists the workflow behind each stage and [`WORKFLOW.md`](./WORKFLOW.md) explains
how to operate and bootstrap it. If anything here disagrees with the automation, fix one of them in the same PR.

## Branch model

| Branch           | Purpose                                            | Lifetime                | Merge method into it        |
| ---------------- | -------------------------------------------------- | ----------------------- | --------------------------- |
| `<type>/<slug>`  | One change: feature, fix, docs, chore, ...         | short, deleted on merge | -                           |
| `dev`            | Integration lane and **default branch**            | permanent               | squash (merge for sync PRs) |
| `next`           | Staging: what the next release will contain        | permanent               | merge commit                |
| `release/vX.Y.Z` | The one in-flight release; carries the new version | temporary               | squash or merge (hotfixes)  |
| `main`           | Production; every commit is a released state       | permanent               | merge commit                |
| `dependabot/*`   | Dependency bumps (bot-owned names)                 | short                   | squash (auto-merge)         |

```
<type>/<slug> --> dev --> next --> release/vX.Y.Z --> main
   squash        merge    cut        draft PR, merge    tag vX.Y.Z + GitHub Release
```

`<type>` is one of `feat fix chore docs ci refactor test perf build style revert ai`. Slugs are lowercase
`[a-z0-9._-]`; an issue number may lead the slug (`feat/123-add-parser`). Git forbids `:` in ref names, so the
Conventional Commit form lives in the **PR title**, not the branch.

## What may target what (enforced by `make pr-guard`, the `guard` check)

1. **`dev`** accepts `<type>/<slug>` heads with a Conventional Commit title.
2. **`next`** accepts only `dev` (or `chore/sync-main-into-next`). Nobody opens feature PRs into `next`.
3. **`main`** accepts only `release/vX.Y.Z`, and `X.Y.Z` must equal the version in the project manifests
   (`scripts/version.sh get`), and those manifests must agree with each other.
4. **`release/vX.Y.Z`** accepts `<type>/<slug>` hotfixes (`fix/<slug>`), same title rule as `dev`.
5. **Stacked PRs** (`feat/b -> feat/a -> dev`) pass when both branches and the title follow the convention.
6. `dependabot/*` heads skip the name and title rules; their titles are made conventional through
   `commit-message.prefix` in `dependabot.yml` (`make dependabot` generates it).

## Commits, titles and SemVer

PR titles (which become the squash commit subject) are Conventional Commits:
`<type>(optional-scope)!: summary`. Individual commits on a feature branch should follow the same shape; the
`commit-msg` hook checks them locally.

The next version is computed from commit subjects and bodies since the newest `vX.Y.Z` tag
(`scripts/semver.sh`, `make bump-info`):

| Signal                                                    | Bump      |
| --------------------------------------------------------- | --------- |
| `type!:` subject, or a `BREAKING CHANGE:` footer          | **major** |
| any `feat:` / `feat(scope):`                              | **minor** |
| anything else (`fix`, `perf`, `docs`, `chore`, `ai`, ...) | **patch** |

- With no tag yet, versioning starts from `v0.0.0`, so the first release is `v0.1.0` (feat) or `v0.0.1`.
- Pre-releases and `-dev.*` tags are ignored when picking the baseline.
- Override a bump on the **Promote to next** workflow (`bump: major|minor|patch`). The chosen version is
  stored on the promote PR as `<!-- release: vX.Y.Z -->` and honored by the cut.
- Never hand-edit versions, `CHANGELOG.md` sections or tags; `make cut-release` writes the version into every
  manifest it finds (`pyproject.toml`, `Cargo.toml`, `package.json`, `app.json`, Xcode `MARKETING_VERSION`,
  or the fallback `VERSION` file) and regenerates the changelog section.

## Merge methods

| Into           | Allowed       | Why                                                                    |
| -------------- | ------------- | ---------------------------------------------------------------------- |
| `dev`          | squash, merge | One commit per feature (the PR title); merge only for sync PRs         |
| `next`, `main` | merge only    | Squashing would collapse a release into one commit and empty the notes |
| `release/v*`   | squash, merge | Hotfix PRs                                                             |

## Required checks and protection

Rulesets live in `.github/rulesets/*.json` and are applied with `make rulesets-apply`:

- `main`, `dev`, `next`: no deletion, no force-push, pull request required, conversations resolved,
  strict up-to-date status checks: **`guard`**, **`check`**, **`Detect hardcoded secrets`**
  (+ **`package`** on `main`).
- `release/v*`: no force-push, same checks, but creation/deletion stay allowed so automation can cut and
  delete it.
- `v*` tags: no deletion, no update, creation restricted to bypass actors.
- Bypass: repository admins, plus the automation GitHub App supplied through `BYPASS_ACTORS_JSON`. Its id
  belongs to the generated repository, so it is never committed.

Drafts run only `guard`. Marking a PR **ready for review** starts `check` (hygiene + tests), and `e2e` when
the base is `next` or `main`, or the PR has the `run-e2e` label.

## Exceptions

- Hotfix: a normal `fix/<slug>` PR into the in-flight `release/vX.Y.Z`; promote to `dev` follows through
  the post-release sync PR.
- Emergency admin bypass is possible but is a policy violation unless followed by a PR that records why.
- Anything with `.github/workflows/` changes needs the automation App to hold the `workflows` permission,
  or the release-branch refresh fails.

## Related files

`.github/LIFECYCLE.md` · `.github/WORKFLOW.md` · `.github/rulesets/` · `.github/settings.yml` ·
`scripts/pr-guard.sh` · `scripts/semver.sh` · `scripts/version.sh` · `scripts/release.sh` ·
`.github/workflows/pr.yml`
