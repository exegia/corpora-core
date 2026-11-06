#!/usr/bin/env bash
# shellcheck source=tests/template/harness.sh
. "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

G="$SCRIPTS/pr-guard.sh"
guard() { BASE="$1" HEAD="$2" TITLE="${3-}" "$G"; }

new_repo
echo "1.2.3" > VERSION

# ── feature -> dev ──
assert_ok   "feat branch + conventional title into dev" guard dev feat/add-parser "feat: add parser"
assert_ok   "scoped + breaking title" guard dev fix/null-check "fix(core)!: reject null"
assert_ok   "issue number in slug" guard dev feat/123-add-parser "feat: add parser"
assert_ok   "ai type" guard dev ai/refine-prompts "ai: refine prompts"
assert_fail "bad branch prefix" guard dev feature/add-parser "feat: add parser"
assert_fail "uppercase branch" guard dev Feat/add-parser "feat: add parser"
assert_fail "no slug" guard dev feat/ "feat: add parser"
assert_fail "title without type" guard dev feat/add-parser "add parser"
assert_fail "title without summary" guard dev feat/add-parser "feat:"
assert_fail "empty title" guard dev feat/add-parser ""

# ── next ──
assert_ok   "dev promotes to next" guard next dev "chore: promote v1.3.0 to next"
assert_ok   "sync branch into next" guard next chore/sync-main-into-next "chore: sync main into next"
assert_fail "feature straight into next" guard next feat/add-parser "feat: add parser"

# ── main ──
assert_ok   "matching release branch into main" guard main release/v1.2.3 "release: v1.2.3"
assert_fail "mismatched release branch" guard main release/v1.2.4 "release: v1.2.4"
assert_fail "feature into main" guard main feat/add-parser "feat: add parser"
assert_fail "dev into main" guard main dev "chore: nope"

# ── release hotfix and stacked PRs ──
assert_ok   "hotfix into release branch" guard release/v1.2.3 fix/typo "fix: typo"
assert_ok   "stacked PR" guard feat/a feat/b "feat: second half"
assert_fail "stacked PR with a bad base" guard wip/a feat/b "feat: second half"
assert_fail "unknown base" guard main-old feat/a "feat: x"

# ── dependabot ──
assert_ok   "dependabot is waved through" guard dev dependabot/npm_and_yarn/x-1.0 "Bump x from 1 to 2"

finish
