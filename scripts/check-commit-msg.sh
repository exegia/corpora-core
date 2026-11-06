#!/usr/bin/env bash
# commit-msg hook: require a Conventional Commit subject.
#
#   scripts/check-commit-msg.sh .git/COMMIT_EDITMSG
#
# Installed by `make setup` through .pre-commit-config.yaml. Merge, revert,
# fixup/squash/amend commits and git's own "Merge ..." messages are allowed.

set -euo pipefail

# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

file="${1:?usage: check-commit-msg.sh <message-file>}"
subject="$(grep -v '^[[:space:]]*#' "$file" | sed -n '1p')"

case "$subject" in
  "Merge "*|"Revert "*|"fixup! "*|"squash! "*|"amend! "*) exit 0 ;;
esac

if ! printf '%s' "$subject" | grep -Eq "^($CC_TYPES)(\\([a-z0-9._/-]+\\))?!?: .+"; then
  {
    echo "Commit subject must be a Conventional Commit:"
    echo "  <type>(optional-scope)!: summary"
    echo "  types: $(printf '%s' "$CC_TYPES" | tr '|' ' ')"
    echo "Got: '$subject'"
  } >&2
  exit 1
fi

if [ "${#subject}" -gt 100 ]; then
  echo "Commit subject is ${#subject} characters; keep it under 72 (hard limit 100)." >&2
  exit 1
fi
