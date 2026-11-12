#!/usr/bin/env bash
# shellcheck source=tests/template/harness.sh
. "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

L="$SCRIPTS/changelog.sh"

new_repo
commit "chore: init"
git tag v0.1.0
commit "feat(ui): add panel"
commit "fix: stop crash"
commit "docs: update readme"
commit "refactor!: rename api"
commit "tidy things up"

sec="$("$L" section 0.2.0 HEAD)"
assert_contains "$sec" "## [0.2.0] - " "heading"
assert_contains "$sec" "### Breaking changes" "breaking group"
assert_contains "$sec" "### Features" "features group"
assert_contains "$sec" "- **ui:** add panel" "scope is bolded"
assert_contains "$sec" "### Bug fixes" "fix group"
assert_contains "$sec" "### Documentation" "docs group"
assert_contains "$sec" "### Other changes" "non-conventional commits are not lost"
assert_not_contains "$sec" "chore: init" "commits before the tag are excluded"

# ── update is idempotent and ordered newest first ──
"$L" update 0.2.0 HEAD >/dev/null 2>&1
"$L" update 0.2.0 HEAD >/dev/null 2>&1
assert_eq "1" "$(grep -c '^## \[0.2.0\]' CHANGELOG.md)" "re-running replaces the section"
assert_contains "$(sed -n '1p' CHANGELOG.md)" "# Changelog" "header preserved"

commit "feat: another"
"$L" update 0.3.0 HEAD >/dev/null 2>&1
first="$(grep -n '^## \[' CHANGELOG.md | sed -n '1p')"
assert_contains "$first" "[0.3.0]" "newest section is first"

# ── extract returns just one section ──
body="$("$L" extract 0.2.0)"
assert_contains "$body" "add panel" "extract has the section body"
assert_not_contains "$body" "## [" "extract has no headings of other sections"
assert_eq "" "$("$L" extract 9.9.9)" "unknown version extracts nothing"

# ── layout: a blank line before each section and none at the end ──
new_repo
printf '# Changelog\n\nHand-written header with no trailing blank line.\n' > CHANGELOG.md
commit "chore: init"
git tag v0.1.0
commit "feat: first"
"$L" update 0.2.0 HEAD >/dev/null 2>&1
assert_eq "" "$(grep -B1 '^## \[0.2.0\]' CHANGELOG.md | sed -n '1p')" "blank line before the new heading"
assert_eq "- first" "$(tail -n 1 CHANGELOG.md)" "no blank lines at the end of the file"
commit "feat: second"
"$L" update 0.3.0 HEAD >/dev/null 2>&1
assert_eq "" "$(grep -B1 '^## \[0.2.0\]' CHANGELOG.md | sed -n '1p')" "older heading keeps its blank line"
assert_eq "0" "$(grep -c '^## \[0.2.0\]' <(tail -n 1 CHANGELOG.md))" "file still ends with a list item"

# ── tidy repairs a file written before the layout fix ──
printf '# Changelog\n\nHeader.\n## [0.1.0] - 2026-01-01\n\n- item\n\n\n' > CHANGELOG.md
"$L" tidy >/dev/null 2>&1
assert_eq "$(printf '# Changelog\n\nHeader.\n\n## [0.1.0] - 2026-01-01\n\n- item')" "$(cat CHANGELOG.md)" "tidy fixes the layout"
assert_eq "0a" "$(tail -c 1 CHANGELOG.md | od -An -tx1 | tr -d ' ')" "tidy keeps one final newline"

finish
