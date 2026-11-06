---
name: branch-and-release
description: Git flow for this template - branch naming, Conventional Commit PR titles, dev to next to main promotion, hotfixes, versioning and a failing guard check. Use when asked to "open a PR", "cut a release", "name a branch", "fix guard", or "hotfix".
---

# Branch and release flow

**When to use:** any time you create a branch, commit, open or retitle a PR, ship a release, or debug a red `guard`/`check`.

## Flow at a glance

1. Branch from `dev` (the DEFAULT branch): `<type>/<slug>`.
   Types: `feat|fix|chore|docs|ci|refactor|test|perf|build|style|revert|ai`.
2. PR into `dev`. Squash merge. The PR title becomes the commit message, so it must be a Conventional Commit: `type(scope)!: summary`.
3. An auto promote PR `dev` -> `next` is opened (merge commit). It runs daily at 22:00 UTC or on demand via the "Promote to next" workflow.
4. A push to `next` cuts `release/vX.Y.Z`: bumps the version in manifests and `CHANGELOG.md`, then opens a DRAFT PR into `main` (merge commit).
5. Merging that PR tags `vX.Y.Z`, creates the GitHub Release, deletes the release branch, and syncs `main` back into `next` and `dev`.

`main` is read-only except for configured bypass actors. Never push to `main`, `next`, or `release/*` directly.

## Day-to-day commands

```sh
git switch dev && git pull
git switch -c feat/add-search
make fmt && make ci          # before pushing
git commit -m "feat(search): add query box"
make pr-guard                # check branch name and PR title rules locally
```

## Versioning

SemVer is derived from Conventional Commits since the last `vX.Y.Z` tag:

- `type!:` or a `BREAKING CHANGE:` footer -> major
- `feat` -> minor
- anything else -> patch

Preview with `make next-version` and `make release-notes`. The "Promote to next" `workflow_dispatch` can override with major/minor/patch. Do not hand-edit versions or `CHANGELOG.md`.

## Required checks

- `guard`: validates branch name, PR title, and base branch policy. Runs on drafts.
- `check`: runs `make ci`. Starts only when the PR is marked ready.
- `Detect hardcoded secrets`: gitleaks scan.

## Reading a failing `guard`

1. Open the failed job log and read the first error line; it names the rule.
2. Bad title: edit the PR title to `type(scope): summary` (lowercase type, colon, space).
3. Bad branch name: rename (`git branch -m`), push, open a new PR from the renamed branch.
4. Wrong base: retarget to `dev`, or to the in-flight `release/vX.Y.Z` for hotfixes.
5. Reproduce locally with `make pr-guard`.

## Stacked PRs

Base the second branch on the first. Open PR 2 against PR 1's branch, then retarget it to `dev` after PR 1 squash-merges and rebase with `git rebase --onto dev <old-base> <branch>`.

## Hotfix

Branch `fix/<slug>` and open the PR into the in-flight `release/vX.Y.Z`, not `dev`. It merges into the release branch and reaches `dev`/`next` through the post-release sync.

## Pitfalls

- PRs from lifecycle branches other than the documented ones are rejected by base policy.
- Draft PRs only run `guard`; mark ready to get `check`.
- A `chore:` title still releases a patch version; use it deliberately.
- Do not rebase or force-push shared `next` or `release/*` branches.
- Never use `--no-verify` to get past hooks.
