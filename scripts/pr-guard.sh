#!/usr/bin/env bash
# Validate a pull request's base branch, head branch name and title.
#
#   BASE=dev HEAD=feat/add-parser TITLE='feat: add parser' scripts/pr-guard.sh
#
# Rules (see .github/BRANCH-AND-RELEASE-POLICY.md):
#   -> main            only from release/vX.Y.Z, and X.Y.Z must equal the project version
#   -> dev, release/*  head <type>/<slug>, title is a Conventional Commit
#   -> next            only from dev (or chore/sync-main-into-next)
#   -> <type>/<slug>   stacked PR: base and head are both <type>/<slug>, title is conventional
#   dependabot/*       always waved through (its branch and title are not renameable)
#
# TRUNK (default main) names the production branch.

set -euo pipefail

# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$(repo_root)"

: "${BASE:?BASE is required}" "${HEAD:?HEAD is required}"
TITLE="${TITLE-}"
TRUNK="${TRUNK:-main}"

BRANCH_RE="^($CC_TYPES)/[a-z0-9][a-z0-9._-]*\$"
TITLE_RE="^($CC_TYPES)(\\([a-z0-9._/-]+\\))?!?: .+"

branch_ok() { printf '%s' "$1" | grep -Eq "$BRANCH_RE"; }
title_ok()  { printf '%s' "$TITLE" | grep -Eq "$TITLE_RE"; }

need_branch() { branch_ok "$2" || die "$1 must be <type>/<slug> where type is one of $CC_TYPES (got '$2')"; }
need_title()  { title_ok || die "PR title must read '<type>(scope)!: summary' with type one of $CC_TYPES (got '$TITLE')"; }

case "$HEAD" in
  dependabot/*)
    echo "guard skipped for dependabot: $HEAD -> $BASE"
    exit 0 ;;
esac

case "$BASE" in
  "$TRUNK")
    printf '%s' "$HEAD" | grep -Eq '^release/v[0-9]+\.[0-9]+\.[0-9]+$' \
      || die "$TRUNK only accepts PRs from release/vX.Y.Z (got '$HEAD')"
    "$(dirname "${BASH_SOURCE[0]}")/version.sh" branch-matches "$HEAD"
    "$(dirname "${BASH_SOURCE[0]}")/version.sh" check
    ;;
  dev|release/v*)
    need_branch "branch" "$HEAD"
    need_title
    ;;
  next)
    [ "$HEAD" = dev ] || [ "$HEAD" = chore/sync-main-into-next ] \
      || die "next only accepts PRs from dev (got '$HEAD')"
    ;;
  */*)
    need_branch "stack base" "$BASE"
    need_branch "branch" "$HEAD"
    need_title
    ;;
  *)
    die "$BASE is not a valid base: target $TRUNK, next, dev, or a <type>/<slug> branch"
    ;;
esac

echo "guard passed: $HEAD -> $BASE"
