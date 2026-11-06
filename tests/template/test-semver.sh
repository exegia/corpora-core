#!/usr/bin/env bash
# shellcheck source=tests/template/harness.sh
. "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

S="$SCRIPTS/semver.sh"

# ── no tags yet ──
new_repo
commit "feat: first thing"
assert_eq "v0.0.0" "$("$S" latest)" "latest is v0.0.0 without tags"
assert_eq "minor" "$("$S" bump HEAD)" "feat without a tag bumps minor"
assert_eq "0.1.0" "$("$S" next auto HEAD)" "next from v0.0.0 with a feat"

# ── after a tag ──
git tag v1.2.3
assert_eq "v1.2.3" "$("$S" latest)" "latest picks the tag"
assert_eq "none" "$("$S" bump HEAD)" "nothing since the tag"
assert_eq "1.2.4" "$("$S" next auto HEAD)" "auto falls back to patch when nothing changed"

commit "docs: tweak readme"
assert_eq "patch" "$("$S" bump HEAD)" "docs bumps patch"

commit "fix(parser): handle eof"
assert_eq "patch" "$("$S" bump HEAD)" "fix bumps patch"
assert_eq "1.2.4" "$("$S" next auto HEAD)" "next patch"

commit "feat(ui): add panel"
assert_eq "minor" "$("$S" bump HEAD)" "feat bumps minor"
assert_eq "1.3.0" "$("$S" next auto HEAD)" "next minor"
assert_eq "2.0.0" "$("$S" next major HEAD)" "explicit major wins"
assert_eq "1.2.4" "$("$S" next patch HEAD)" "explicit patch wins"

commit "refactor!: drop legacy api"
assert_eq "major" "$("$S" bump HEAD)" "bang subject bumps major"
assert_eq "2.0.0" "$("$S" next auto HEAD)" "next major"

# ── BREAKING CHANGE footer ──
new_repo
commit "chore: init"
git tag v0.4.0
commit "feat: add thing" "BREAKING CHANGE: the config format changed"
assert_eq "major" "$("$S" bump HEAD)" "BREAKING CHANGE footer bumps major"

# ── pre-release tags never set the baseline ──
new_repo
commit "chore: init"
git tag v1.0.0
git tag v2.0.0-dev.5
commit "fix: something"
assert_eq "v1.0.0" "$("$S" latest)" "dev candidate tags are ignored"

# ── bad input ──
assert_fail "unknown revision is an error" "$S" bump no-such-ref
assert_fail "bad bump word is an error" "$S" next sideways HEAD

finish
