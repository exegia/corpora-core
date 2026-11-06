#!/usr/bin/env bash
# Release pipeline: dev -> next -> release/vX.Y.Z -> main. Each subcommand is one
# CI step, so anything the workflows do can be reproduced locally with `make`.
# The model is documented in .github/WORKFLOW.md.
#
#   bootstrap-lanes     create origin/next and origin/dev when missing
#   promote-pr          open or refresh the dev -> next PR           (env VERSION, BUMP)
#   cut-release         cut or refresh release/v<VERSION> from next   (env VERSION)
#   release-pr          open or refresh the draft release PR into main (env BRANCH)
#   tag-release         tag HEAD as v<project version> and publish the GitHub Release
#   delete-branch       delete a remote branch, tolerating one already gone (env BRANCH)
#   sync-lanes          merge main back into next and dev through PRs
#   cleanup-cycle       delete merged remote feature branches and stale release/v*
#   cleanup-local       delete local feature/release branches whose remote is gone
#   release-notes       print "- subject" lines for RANGE (default origin/main..HEAD)
#
# Environment: TRUNK (main), GH_REPO, VERSION, BUMP, BRANCH, RANGE,
#              VERSION_CMD (replace `version.sh set`, e.g. for monorepos).

set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib.sh
. "$SCRIPTS/lib.sh"
cd "$(repo_root)"

TRUNK="${TRUNK:-main}"
GH_REPO="${GH_REPO:-$(git config --get remote.origin.url 2>/dev/null | sed -E 's,.*github\.com[:/],,; s,\.git$,,')}"
export GH_REPO

fetch_lane() { git fetch --quiet --force origin "+refs/heads/$1:refs/remotes/origin/$1"; }

branch_exists() { git ls-remote --exit-code --heads origin "$1" >/dev/null 2>&1; }

open_pr_number() { # open_pr_number <base> <head>
  gh pr list --base "$1" --head "$2" --state open --json number --jq '.[0].number // empty'
}

cmd_bootstrap_lanes() {
  local ver src
  git fetch --quiet --force --tags origin "+refs/heads/$TRUNK:refs/remotes/origin/$TRUNK"
  if branch_exists next; then echo "origin/next already exists"
  else
    git push origin "refs/remotes/origin/$TRUNK:refs/heads/next"
    echo "created origin/next from $TRUNK"
  fi
  if branch_exists dev; then echo "origin/dev already exists"
  else
    ver="$(git ls-remote --heads origin 'release/v*' \
      | awk '{print $2}' | sed 's|refs/heads/release/v||' \
      | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' \
      | sort -t. -k1,1n -k2,2n -k3,3n | tail -1 || true)"
    if [ -n "$ver" ]; then src="release/v$ver"; else src="$TRUNK"; fi
    git fetch --quiet origin "+refs/heads/$src:refs/remotes/origin/$src"
    git push origin "refs/remotes/origin/$src:refs/heads/dev"
    echo "created origin/dev from $src"
  fi
}

cmd_promote_pr() {
  : "${VERSION:?VERSION is required}"
  local bump="${BUMP:-patch}" ahead stat notes body num
  git fetch --quiet --force origin "+refs/heads/dev:refs/remotes/origin/dev" "+refs/heads/next:refs/remotes/origin/next"
  ahead="$(git rev-list --count origin/next..origin/dev)"
  if [ "$ahead" -eq 0 ]; then echo "dev is not ahead of next: nothing to promote"; return 0; fi

  stat="$(git diff --shortstat origin/next...origin/dev || true)"
  notes="$("$SCRIPTS/changelog.sh" section "$VERSION" origin/dev | sed '1,2d')"
  body="$(mktemp)"
  {
    printf 'Promote **v%s** (`%s` bump, %s commits ahead of `next`).\n' "$VERSION" "$bump" "$ahead"
    printf '<!-- release: v%s -->\n\n' "$VERSION"
    printf '%s\n\n' "${stat:-0 files changed}"
    printf '## Changes\n\n%s\n' "$notes"
  } > "$body"

  num="$(open_pr_number next dev)"
  if [ -n "$num" ]; then
    gh pr edit "$num" --title "chore: promote v$VERSION to next" --body-file "$body"
    echo "refreshed promote PR #$num"
  else
    gh pr create --base next --head dev --title "chore: promote v$VERSION to next" --body-file "$body"
    num="$(open_pr_number next dev)"
    echo "opened promote PR #$num"
  fi
  rm -f "$body"
  gh pr merge "$num" --auto --merge
}

cmd_cut_release() {
  local existing version="${VERSION:-}" body branch files
  git fetch --quiet --force origin "+refs/heads/next:refs/remotes/origin/next" "+refs/heads/$TRUNK:refs/remotes/origin/$TRUNK"
  if git diff --quiet "origin/$TRUNK" origin/next; then
    echo "next and $TRUNK have the same tree: nothing to cut"; return 0
  fi

  existing="$(gh pr list --base "$TRUNK" --state open --json headRefName \
    --jq '[.[] | select(.headRefName | test("^release/v[0-9]"))] | .[0].headRefName // empty')"
  if [ -n "$existing" ]; then
    version="${existing#release/v}"
    echo "in-flight $existing: refreshing at v$version"
  elif [ -z "$version" ]; then
    # 1) the version recorded on the most recently merged promote PR
    body="$(gh pr list --base next --head dev --state merged --limit 1 --json body --jq '.[0].body // empty')"
    version="$(printf '%s' "$body" | sed -n 's/.*<!-- release: v\([0-9][0-9.]*\) -->.*/\1/p')"
    # 2) otherwise compute it from the Conventional Commits on next
    if [ -z "$version" ]; then version="$("$SCRIPTS/semver.sh" next auto origin/next)"; fi
  fi
  is_semver "$version" || die "could not determine a valid VERSION to cut (got '$version')"

  branch="release/v$version"
  if git fetch --quiet origin "+refs/heads/$branch:refs/remotes/origin/$branch" 2>/dev/null; then
    git checkout --quiet -B "$branch" "origin/$branch"
    git merge --quiet --no-edit -X theirs origin/next
  else
    git checkout --quiet -B "$branch" origin/next
  fi

  if [ -n "${VERSION_CMD:-}" ]; then VERSION="$version" bash -o pipefail -c "$VERSION_CMD"
  else "$SCRIPTS/version.sh" set "$version"; fi
  "$SCRIPTS/changelog.sh" update "$version" origin/next
  "$SCRIPTS/version.sh" refresh-locks

  if [ -n "${VERSION_CMD:-}" ]; then git add -u; fi
  for files in $("$SCRIPTS/version.sh" files); do git add -- "$files"; done
  if git diff --cached --quiet; then echo "version files already at $version"
  else git commit --quiet -m "chore(release): open v$version"; fi
  git push --quiet -u origin "$branch"
  echo "updated $branch"
}

cmd_release_pr() {
  local branch="${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}" version notes body num cl
  version="${branch#release/v}"
  git fetch --quiet origin "$TRUNK:refs/remotes/origin/$TRUNK" "$branch:refs/remotes/origin/$branch"

  cl="$(mktemp)"
  git show "origin/$branch:CHANGELOG.md" > "$cl" 2>/dev/null || : > "$cl"
  notes="$(CHANGELOG="$cl" "$SCRIPTS/changelog.sh" extract "$version" 2>/dev/null || true)"
  rm -f "$cl"
  [ -n "$notes" ] || notes="$(RANGE="origin/$TRUNK..origin/$branch" cmd_release_notes)"

  body="$(mktemp)"
  {
    printf 'Release **v%s**.\n\n## Changes\n\n%s\n' "$version" "$notes"
    printf '\n---\nRefreshed automatically whenever `%s` is updated from `next`.\n' "$branch"
  } > "$body"

  num="$(open_pr_number "$TRUNK" "$branch")"
  if [ -n "$num" ]; then
    gh pr edit "$num" --body-file "$body"
    echo "refreshed release PR #$num"
  else
    gh pr create --draft --base "$TRUNK" --head "$branch" --title "release: v$version" --body-file "$body"
  fi
  rm -f "$body"
}

cmd_tag_release() {
  local version tag notes
  version="$("$SCRIPTS/version.sh" get)"
  tag="v$version"
  if gh api "repos/$GH_REPO/git/ref/tags/$tag" >/dev/null 2>&1; then
    echo "$tag already exists: skipping"; return 0
  fi
  notes="$(mktemp)"
  "$SCRIPTS/changelog.sh" extract "$version" > "$notes" 2>/dev/null || : > "$notes"
  if [ -s "$notes" ]; then
    gh release create "$tag" --target "$(git rev-parse HEAD)" --title "$tag" --notes-file "$notes"
  else
    gh release create "$tag" --target "$(git rev-parse HEAD)" --title "$tag" --generate-notes
  fi
  rm -f "$notes"
  echo "released $tag"
}

cmd_delete_branch() {
  : "${BRANCH:?BRANCH is required}"
  if gh api -X DELETE "repos/$GH_REPO/git/refs/heads/$BRANCH" >/dev/null 2>&1; then echo "deleted $BRANCH"
  else echo "$BRANCH was already gone"; fi
}

cmd_sync_lanes() {
  local lane head body num
  cmd_bootstrap_lanes
  git fetch --quiet --force origin \
    "+refs/heads/$TRUNK:refs/remotes/origin/$TRUNK" \
    "+refs/heads/next:refs/remotes/origin/next" \
    "+refs/heads/dev:refs/remotes/origin/dev"
  for lane in next dev; do
    head="chore/sync-main-into-$lane"
    git checkout --quiet -B "$head" "origin/$lane"
    if git merge-base --is-ancestor "origin/$TRUNK" HEAD; then
      echo "$lane already contains $TRUNK"; continue
    fi
    git merge --quiet --no-edit "origin/$TRUNK"
    git push --force-with-lease --quiet -u origin "$head"
    body="$(mktemp)"
    printf 'Sync **%s** into `%s` after the production release.\n' "$TRUNK" "$lane" > "$body"
    num="$(open_pr_number "$lane" "$head")"
    if [ -n "$num" ]; then
      gh pr edit "$num" --title "chore: sync main into $lane" --body-file "$body"
      echo "refreshed sync PR #$num into $lane"
    else
      gh pr create --base "$lane" --head "$head" --title "chore: sync main into $lane" --body-file "$body"
      num="$(open_pr_number "$lane" "$head")"
      echo "opened sync PR #$num into $lane"
    fi
    rm -f "$body"
    gh pr merge "$num" --auto --merge
  done
}

cmd_cleanup_cycle() {
  local ref open
  git fetch --quiet --prune origin
  fetch_lane dev
  for ref in $(git branch -r --merged origin/dev | sed 's/^[[:space:]]*origin\///' | grep -E "^($CC_TYPES)/" || true); do
    BRANCH="$ref" cmd_delete_branch
  done
  open="$(gh pr list --base "$TRUNK" --state open --json headRefName \
    --jq '[.[].headRefName | select(startswith("release/v"))] | join(" ")')"
  for ref in $(git ls-remote --heads origin 'release/v*' | awk '{print $2}' | sed 's|refs/heads/||'); do
    case " $open " in *" $ref "*) continue ;; esac
    BRANCH="$ref" cmd_delete_branch
  done
}

cmd_cleanup_local() {
  local current b
  git fetch --prune --quiet origin
  current="$(git rev-parse --abbrev-ref HEAD)"
  for b in $(git branch --format='%(refname:short)' | grep -E "^($CC_TYPES)/|^release/v" || true); do
    [ "$b" = "$current" ] && continue
    if branch_exists "$b"; then continue; fi
    git branch -D "$b"
  done
}

cmd_release_notes() {
  git log --no-merges --reverse --pretty='- %s' "${RANGE:-origin/$TRUNK..HEAD}" | grep . \
    || echo '- _Nothing merged yet._'
}

main() {
  local cmd="${1:-}"; [ "$#" -gt 0 ] && shift
  case "$cmd" in
    bootstrap-lanes) cmd_bootstrap_lanes ;;
    promote-pr)      cmd_promote_pr ;;
    cut-release)     cmd_cut_release ;;
    release-pr)      cmd_release_pr ;;
    tag-release)     cmd_tag_release ;;
    delete-branch)   cmd_delete_branch ;;
    sync-lanes)      cmd_sync_lanes ;;
    cleanup-cycle)   cmd_cleanup_cycle ;;
    cleanup-local)   cmd_cleanup_local ;;
    release-notes)   cmd_release_notes ;;
    *) sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; [ -z "$cmd" ] || exit 2 ;;
  esac
}

main "$@"
