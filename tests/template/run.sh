#!/usr/bin/env bash
# Run every tests/template/test-*.sh. Used by `make selftest` and CI.
# These test the template's own automation (scripts/), not your product code.

set -u
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
failed=0

for t in "$dir"/test-*.sh; do
  bash "$t" || failed=$((failed + 1))
done

if [ "$failed" -ne 0 ]; then
  echo "selftest: $failed test file(s) failed" >&2
  exit 1
fi
echo "selftest: all passed"
