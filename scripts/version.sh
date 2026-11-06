#!/usr/bin/env bash
# Read and write the project version across every manifest this template knows.
#
#   scripts/version.sh get                 the project version (first manifest found)
#   scripts/version.sh set X.Y.Z           write X.Y.Z into every manifest present
#   scripts/version.sh files               tracked files `set` may have touched (for `git add`)
#   scripts/version.sh refresh-locks       best-effort lockfile refresh after `set`
#   scripts/version.sh check               fail when manifests disagree with each other
#   scripts/version.sh branch-matches <b>  fail unless branch b is release/v<version>
#
# Manifests, in priority order:
#   pyproject.toml ([project] / [tool.poetry]) · Cargo.toml ([package] /
#   [workspace.package]) · package.json · app.json (expo.version) · *.xcodeproj
#   (MARKETING_VERSION). The VERSION file is the fallback while none of those
#   declares a version; delete it once one does.
#
# Root-level manifests only. Monorepos with per-package versions should run their
# own release tooling and set VERSION_CMD (see `scripts/release.sh cut-release`).

set -euo pipefail

# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$(repo_root)"

# toml_get <file> <section-regex>: first `version = "..."` inside a matching section.
# Section regexes use [.] rather than \. because awk -v mangles backslashes.
toml_get() {
  awk -v want="$2" '
    /^\[/ { s = $0; gsub(/[[:space:]]/, "", s); insec = (s ~ want); next }
    insec && /^version[[:space:]]*=/ {
      n = split($0, a, "\""); if (n >= 3) { print a[2]; exit }
    }
  ' "$1"
}

toml_set() { # toml_set <file> <section-regex> <version>
  local tmp; tmp="$(mktemp)"
  awk -v want="$2" -v ver="$3" '
    /^\[/ { s = $0; gsub(/[[:space:]]/, "", s); insec = (s ~ want) }
    insec && !done && /^version[[:space:]]*=[[:space:]]*"/ {
      print "version = \"" ver "\""; done = 1; next
    }
    { print }
  ' "$1" > "$tmp"
  cat "$tmp" > "$1"; rm -f "$tmp"
}

PY_SECTIONS='^[[](project|tool[.]poetry)[]]$'
CARGO_SECTIONS='^[[](package|workspace[.]package)[]]$'

pbxproj_files() { ls -d ./*.xcodeproj/project.pbxproj 2>/dev/null || true; }

# Emit "<label>\t<version>" for each stack manifest that declares one.
read_manifests() {
  local v f
  if [ -f pyproject.toml ]; then v="$(toml_get pyproject.toml "$PY_SECTIONS")"; [ -n "$v" ] && printf 'pyproject.toml\t%s\n' "$v"; fi
  if [ -f Cargo.toml ]; then v="$(toml_get Cargo.toml "$CARGO_SECTIONS")"; [ -n "$v" ] && printf 'Cargo.toml\t%s\n' "$v"; fi
  if [ -f package.json ] && have jq; then
    v="$(jq -r '.version // empty' package.json)"; [ -n "$v" ] && printf 'package.json\t%s\n' "$v"
  fi
  if [ -f app.json ] && have jq; then
    v="$(jq -r '.expo.version // empty' app.json)"; [ -n "$v" ] && printf 'app.json\t%s\n' "$v"
  fi
  for f in $(pbxproj_files); do
    v="$(sed -nE 's/.*MARKETING_VERSION = ([0-9][0-9.]*);.*/\1/p' "$f" | sed -n '1p')"
    [ -n "$v" ] && printf '%s\t%s\n' "$f" "$v"
  done
  return 0
}

# VERSION is the fallback for repos whose stack has no versioned manifest yet
# (the bare template). Once a manifest declares a version, delete VERSION.
read_all() {
  local out v
  out="$(read_manifests)"
  if [ -n "$out" ]; then printf '%s\n' "$out"
  elif [ -f VERSION ]; then
    v="$(tr -d '[:space:]' < VERSION)"
    [ -z "$v" ] || printf 'VERSION\t%s\n' "$v"
  fi
  return 0
}

cmd_get() {
  local first; first="$(read_all | sed -n '1p' | cut -f2)"
  [ -n "$first" ] || die "no version found (add VERSION, pyproject.toml, Cargo.toml, package.json or app.json)"
  printf '%s\n' "$first"
}

cmd_check() {
  local distinct; distinct="$(read_all | cut -f2 | sort -u)"
  if [ "$(printf '%s\n' "$distinct" | grep -c .)" -gt 1 ]; then
    err "manifests disagree on the version:"
    read_all | awk -F'\t' '{ printf "  %-40s %s\n", $1, $2 }' >&2
    return 1
  fi
}

cmd_set() {
  local v="${1:-}" f tmp
  is_semver "$v" || die "usage: version.sh set X.Y.Z (got '$v')"

  [ -f VERSION ] && printf '%s\n' "$v" > VERSION
  [ -f pyproject.toml ] && [ -n "$(toml_get pyproject.toml "$PY_SECTIONS")" ] && toml_set pyproject.toml "$PY_SECTIONS" "$v"
  [ -f Cargo.toml ] && [ -n "$(toml_get Cargo.toml "$CARGO_SECTIONS")" ] && toml_set Cargo.toml "$CARGO_SECTIONS" "$v"

  if [ -f package.json ] && [ -n "$(jq -r '.version // empty' package.json 2>/dev/null)" ]; then
    tmp="$(mktemp)"
    awk -v ver="$v" '
      !d && /^[[:space:]]*"version"[[:space:]]*:/ {
        sub(/"version"[[:space:]]*:[[:space:]]*"[^"]*"/, "\"version\": \"" ver "\""); d = 1
      }
      { print }
    ' package.json > "$tmp"
    cat "$tmp" > package.json; rm -f "$tmp"
  fi

  if [ -f app.json ] && [ -n "$(jq -r '.expo.version // empty' app.json 2>/dev/null)" ]; then
    tmp="$(mktemp)"
    jq --arg v "$v" '.expo.version = $v' app.json > "$tmp" && cat "$tmp" > app.json
    rm -f "$tmp"
  fi

  for f in $(pbxproj_files); do
    tmp="$(mktemp)"
    sed -E "s/(MARKETING_VERSION = )[0-9][0-9.]*;/\\1$v;/" "$f" > "$tmp"
    cat "$tmp" > "$f"; rm -f "$tmp"
  done

  local bad
  bad="$(read_all | awk -F'\t' -v v="$v" '$2 != v { print $1 }')"
  [ -z "$bad" ] || die "could not set $v in: $(printf '%s' "$bad" | tr '\n' ' ')"
  ok "version is now $v ($(read_all | cut -f1 | tr '\n' ' '))"
}

cmd_files() {
  local f
  for f in VERSION pyproject.toml uv.lock Cargo.toml Cargo.lock package.json package-lock.json \
           pnpm-lock.yaml app.json CHANGELOG.md $(pbxproj_files); do
    [ -e "$f" ] && printf '%s\n' "$f"
  done
  return 0
}

cmd_refresh_locks() {
  if [ -f uv.lock ] && have uv; then uv lock --quiet || warn "uv lock failed"; fi
  if [ -f Cargo.lock ] && have cargo; then cargo update --workspace --quiet || warn "cargo update failed"; fi
  if [ -f package-lock.json ] && have npm; then
    npm install --package-lock-only --ignore-scripts --silent || warn "npm lockfile refresh failed"
  fi
  if [ -f pnpm-lock.yaml ] && have pnpm; then
    pnpm install --lockfile-only --silent || warn "pnpm lockfile refresh failed"
  fi
  return 0
}

cmd_branch_matches() {
  local branch="${1:-}" want
  want="release/v$(cmd_get)"
  [ "$want" = "$branch" ] || die "project version says $want but the branch is $branch"
}

main() {
  local cmd="${1:-}"; [ "$#" -gt 0 ] && shift
  case "$cmd" in
    get)            cmd_get ;;
    set)            cmd_set "$@" ;;
    files)          cmd_files ;;
    refresh-locks)  cmd_refresh_locks ;;
    check)          cmd_check ;;
    branch-matches) cmd_branch_matches "$@" ;;
    *) sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; [ -z "$cmd" ] || exit 2 ;;
  esac
}

main "$@"
