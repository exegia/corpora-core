#!/usr/bin/env bash
# Semantic-version math driven by Conventional Commits.
#
#   scripts/semver.sh latest              newest vX.Y.Z tag (v0.0.0 when none)
#   scripts/semver.sh bump [TO]           none|patch|minor|major for latest-tag..TO (default origin/dev)
#   scripts/semver.sh next [BUMP] [TO]    the next version number; BUMP is auto (default),
#                                         major, minor or patch
#
# Rules (applied to commit subjects and bodies in latest-tag..TO, merges ignored):
#   `type!:` subject or a `BREAKING CHANGE:` footer  -> major
#   `feat:` / `feat(scope):`                         -> minor
#   anything else (fix, perf, docs, chore, ...)      -> patch
#
# Feature PRs are squash-merged into dev with the PR title as the commit subject,
# so the PR-title rule enforced by `make pr-guard` is what makes this reliable.

set -euo pipefail

# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$(repo_root)"

cmd_latest() { local t; t="$(latest_tag)"; printf '%s\n' "${t:-v0.0.0}"; }

cmd_bump() {
  local to="${1:-origin/dev}" range subjects bodies
  git rev-parse --verify --quiet "$to^{commit}" >/dev/null || die "unknown revision: $to"
  range="$(unreleased_range "$to")"
  subjects="$(git log --no-merges --format=%s "$range")"
  if [ -z "$subjects" ]; then echo none; return 0; fi
  bodies="$(git log --no-merges --format=%b "$range")"

  if printf '%s\n' "$bodies" | grep -Eq '^BREAKING[ -]CHANGE(:| )' \
     || printf '%s\n' "$subjects" | grep -Eq '^[a-z]+(\([^)]*\))?!:'; then
    echo major
  elif printf '%s\n' "$subjects" | grep -Eq '^feat(\([^)]*\))?:'; then
    echo minor
  else
    echo patch
  fi
}

cmd_next() {
  local bump="${1:-auto}" to="${2:-origin/dev}" cur major minor patch
  if [ "$bump" = auto ]; then
    bump="$(cmd_bump "$to")"
    [ "$bump" != none ] || bump="patch"
  fi
  cur="$(cmd_latest)"; cur="${cur#v}"
  IFS=. read -r major minor patch <<EOF
$cur
EOF
  case "$bump" in
    major) printf '%d.0.0\n' $((major + 1)) ;;
    minor) printf '%d.%d.0\n' "$major" $((minor + 1)) ;;
    patch) printf '%d.%d.%d\n' "$major" "$minor" $((patch + 1)) ;;
    *) die "BUMP must be auto, major, minor or patch (got '$bump')" ;;
  esac
}

main() {
  local cmd="${1:-}"; [ "$#" -gt 0 ] && shift
  case "$cmd" in
    latest) cmd_latest ;;
    bump)   cmd_bump "$@" ;;
    next)   cmd_next "$@" ;;
    *) sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; [ -z "$cmd" ] || exit 2 ;;
  esac
}

main "$@"
