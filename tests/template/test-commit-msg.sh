#!/usr/bin/env bash
# shellcheck source=tests/template/harness.sh
. "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

C="$SCRIPTS/check-commit-msg.sh"
msg() { local f; f="$(mktemp)"; printf '%b' "$1" > "$f"; "$C" "$f"; local rc=$?; rm -f "$f"; return $rc; }

assert_ok   "plain type"            msg "feat: add parser\n"
assert_ok   "scope"                 msg "fix(core): handle nil\n"
assert_ok   "breaking bang"         msg "refactor!: drop v1\n"
assert_ok   "body and comments"     msg "docs: explain release\n\nWhy this matters.\n# a comment\n"
assert_ok   "git merge message"     msg "Merge branch 'dev' into feat/x\n"
assert_ok   "revert message"        msg "Revert \"feat: add parser\"\n"
assert_ok   "fixup commit"          msg "fixup! feat: add parser\n"
assert_fail "missing type"          msg "add parser\n"
assert_fail "unknown type"          msg "feature: add parser\n"
assert_fail "no summary"            msg "feat:\n"
assert_fail "missing space"         msg "feat:add parser\n"
assert_fail "overlong subject"      msg "feat: $(printf 'x%.0s' $(seq 1 120))\n"

finish
