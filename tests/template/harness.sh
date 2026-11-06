#!/usr/bin/env bash
# Tiny assertion harness for the template's own tests. Source it from a test file.
# bash 3.2 compatible. Each test file runs in its own process (see run.sh).

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC2034  # used by the test files that source this harness
SCRIPTS="$ROOT/scripts"

export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.com
export GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.com
export NO_COLOR=1
unset CI GITHUB_ACTIONS STACKS CI_RUNNERS MATRIX_RUNNERS NODE_PM
for _t in INSTALL FMT LINT TYPECHECK TEST E2E EVAL BUILD PACK DEV; do unset "${_t}_CMD"; done

_pass=0
_fail=0
_tmp_dirs=""

_cleanup() { [ -z "$_tmp_dirs" ] || rm -rf $_tmp_dirs; }
trap _cleanup EXIT

# new_repo: make a throwaway git repo and cd into it.
new_repo() {
  local d; d="$(mktemp -d)"
  _tmp_dirs="$_tmp_dirs $d"
  cd "$d" || exit 1
  git init -q -b main
  git config commit.gpgsign false
  git config tag.gpgsign false
}

commit() { # commit <subject> [body]
  echo "$RANDOM$RANDOM" >> .history
  git add -A
  if [ -n "${2:-}" ]; then git commit -q -m "$1" -m "$2"; else git commit -q -m "$1"; fi
}

_ok()  { _pass=$((_pass + 1)); }
_bad() { _fail=$((_fail + 1)); printf '  FAIL: %s\n' "$1" >&2; shift; [ "$#" -eq 0 ] || printf '        %s\n' "$@" >&2; }

assert_eq() { # assert_eq <expected> <actual> <message>
  if [ "$1" = "$2" ]; then _ok; else _bad "$3" "expected: '$1'" "actual:   '$2'"; fi
}

assert_contains() { # assert_contains <haystack> <needle> <message>
  case "$1" in *"$2"*) _ok ;; *) _bad "$3" "missing: '$2'" ;; esac
}

assert_not_contains() {
  case "$1" in *"$2"*) _bad "$3" "unexpected: '$2'" ;; *) _ok ;; esac
}

assert_ok() { # assert_ok <message> <command...>
  local msg="$1"; shift
  if "$@" >/dev/null 2>&1; then _ok; else _bad "$msg" "command failed: $*"; fi
}

assert_fail() { # assert_fail <message> <command...>
  local msg="$1"; shift
  if "$@" >/dev/null 2>&1; then _bad "$msg" "command unexpectedly succeeded: $*"; else _ok; fi
}

finish() {
  printf '%s: %d passed, %d failed\n' "$(basename "$0")" "$_pass" "$_fail"
  [ "$_fail" -eq 0 ]
}
