#!/usr/bin/env bash
# Shared helpers for the scripts in this directory. Source it, do not execute it.
#
# Written for bash 3.2 (the macOS default): no associative arrays, no mapfile,
# no ${var,,}. Keep it that way so `make` works on a stock Mac and in CI alike.

# Conventional-commit types accepted in branch names, PR titles and commits.
# Keep in step with .gitmessage, CONTRIBUTING.md and .github/PULL_REQUEST_TEMPLATE.md.
# shellcheck disable=SC2034  # used by the scripts that source this file
CC_TYPES='feat|fix|chore|docs|ci|refactor|test|perf|build|style|revert|ai'

DIST_DIR="${DIST_DIR:-dist}"

# ── Output ───────────────────────────────────────────────────────────────────

if [ -t 2 ] && [ -z "${NO_COLOR:-}" ]; then
  _c_dim=$'\033[2m'; _c_red=$'\033[31m'; _c_yellow=$'\033[33m'; _c_green=$'\033[32m'; _c_off=$'\033[0m'
else
  _c_dim=''; _c_red=''; _c_yellow=''; _c_green=''; _c_off=''
fi

log()  { printf '%s\n' "$*" >&2; }
info() { printf '%s==>%s %s\n' "$_c_dim" "$_c_off" "$*" >&2; }
ok()   { printf '%s ok%s %s\n' "$_c_green" "$_c_off" "$*" >&2; }
skip() { printf '%s -- skip%s %s\n' "$_c_dim" "$_c_off" "$*" >&2; }

warn() {
  if [ -n "${GITHUB_ACTIONS:-}" ]; then printf '::warning::%s\n' "$*" >&2
  else printf '%swarn:%s %s\n' "$_c_yellow" "$_c_off" "$*" >&2; fi
}

err() {
  if [ -n "${GITHUB_ACTIONS:-}" ]; then printf '::error::%s\n' "$*" >&2
  else printf '%serror:%s %s\n' "$_c_red" "$_c_off" "$*" >&2; fi
}

die() { err "$*"; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

need() {
  local t
  for t in "$@"; do have "$t" || die "required tool not found: $t"; done
}

# Repository root, regardless of the caller's working directory.
repo_root() { git rev-parse --show-toplevel 2>/dev/null || pwd; }

# Collapse log output in GitHub Actions.
group_start() { if [ -n "${GITHUB_ACTIONS:-}" ]; then printf '::group::%s\n' "$*"; else info "$*"; fi; }
group_end()   { if [ -n "${GITHUB_ACTIONS:-}" ]; then printf '::endgroup::\n'; fi; }

# True when running in CI (lockfiles are then enforced).
in_ci() { [ -n "${CI:-}" ] || [ -n "${GITHUB_ACTIONS:-}" ]; }

# ── Stack detection ──────────────────────────────────────────────────────────
# Build stacks (have tooling to run): python node rust swift
# Flavors (detail only, used for CI setup + labels): typescript react expo gpui

_has_glob() { # _has_glob "*.xcodeproj" -> true if any match in the current dir
  local f
  for f in $1; do [ -e "$f" ] && return 0; done
  return 1
}

pkg_has_dep() { # pkg_has_dep <name> -> true when package.json lists the dependency
  [ -f package.json ] && have jq || return 1
  jq -e --arg n "$1" \
    '((.dependencies // {}) + (.devDependencies // {}) + (.peerDependencies // {})) | has($n)' \
    package.json >/dev/null 2>&1
}

pkg_script() { # pkg_script <name> -> script body, empty when absent
  [ -f package.json ] && have jq || return 0
  jq -r --arg n "$1" '.scripts[$n] // empty' package.json 2>/dev/null
}

detect_stacks() {
  if [ -n "${STACKS:-}" ]; then
    # shellcheck disable=SC2086
    printf '%s\n' $STACKS
    return 0
  fi
  [ -f pyproject.toml ] || [ -f requirements.txt ] && echo python
  [ -f package.json ] && echo node
  [ -f Cargo.toml ] && echo rust
  if [ -f Package.swift ] || _has_glob '*.xcodeproj' || _has_glob '*.xcworkspace'; then echo swift; fi
  return 0
}

detect_tags() {
  local s
  for s in $(detect_stacks); do
    echo "$s"
    case "$s" in
      node)
        { [ -f tsconfig.json ] || pkg_has_dep typescript; } && echo typescript
        pkg_has_dep react && echo react
        pkg_has_dep expo && echo expo
        ;;
      rust)
        if grep -qE '^[[:space:]]*gpui[A-Za-z0-9_-]*[[:space:]]*(=|\.)' Cargo.toml 2>/dev/null \
          || grep -qE 'name = "gpui"' Cargo.lock 2>/dev/null \
          || grep -rqE '^[[:space:]]*gpui[A-Za-z0-9_-]*[[:space:]]*(=|\.)' crates/*/Cargo.toml 2>/dev/null; then
          echo gpui
        fi
        ;;
    esac
  done
  return 0
}

stack_active() { detect_stacks | grep -qx "$1"; }
tag_active()   { detect_tags   | grep -qx "$1"; }

# ── Node package manager ─────────────────────────────────────────────────────

node_pm() {
  if [ -n "${NODE_PM:-}" ]; then echo "$NODE_PM"; return; fi
  local field=''
  have jq && field="$(jq -r '.packageManager // empty' package.json 2>/dev/null | sed -E 's/@.*//')"
  if   [ -f bun.lock ] || [ -f bun.lockb ]; then echo bun
  elif [ -f pnpm-lock.yaml ]; then echo pnpm
  elif [ -f yarn.lock ]; then echo yarn
  elif [ -f package-lock.json ]; then echo npm
  elif [ -n "$field" ]; then echo "$field"
  else echo npm
  fi
}

# ── Version helpers ──────────────────────────────────────────────────────────

# Latest stable tag (vX.Y.Z, no suffix) or empty. Pure-numeric sort so it works
# with BSD sort too.
latest_tag() {
  git tag -l 'v[0-9]*' 2>/dev/null \
    | { grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' || true; } \
    | sed 's/^v//' \
    | sort -t. -k1,1n -k2,2n -k3,3n \
    | tail -1 \
    | sed 's/^/v/'
}

# Revision range of unreleased work ending at <to>: "vX.Y.Z..<to>", or just <to>
# when nothing has been tagged yet.
unreleased_range() {
  local to="${1:-HEAD}" tag
  tag="$(latest_tag)"
  if [ -n "$tag" ]; then printf '%s..%s' "$tag" "$to"; else printf '%s' "$to"; fi
}

is_semver() { printf '%s' "$1" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; }

# Collapse "" / unset to a default.
default() { if [ -n "${1:-}" ]; then printf '%s' "$1"; else printf '%s' "$2"; fi; }
