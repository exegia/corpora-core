#!/usr/bin/env bash
# shellcheck source=tests/template/harness.sh
. "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

new_repo
commit "chore: initial"
git init -q --bare "$PWD/remote.git"
git remote add origin "$PWD/remote.git"
git push -q origin main
git switch -q -c next
git commit -q --allow-empty -m "chore: sync next"
git push -q origin next
git switch -q main
git switch -q -c dev
git commit -q --allow-empty -m "chore: sync dev"
git push -q origin dev

mkdir fakebin
cat > fakebin/gh <<'SH'
#!/usr/bin/env bash
case "$1 $2" in
  "release view")
    [ -n "${FAKE_DRAFT:-}" ] || exit 1
    printf '%s\n' "$FAKE_DRAFT"
    ;;
  "release create"|"release upload"|"release edit")
    printf '%s\n' "$*" >> "$FAKE_LOG"
    ;;
  *) exit 90 ;;
esac
SH
chmod +x fakebin/gh
export FAKE_LOG="$PWD/gh-calls"
export GH_REPO=example/test
export PATH="$PWD/fakebin:$PATH"

output="$(VERSION=0.1.1 "$SCRIPTS/release.sh" promote-pr 2>&1)"
assert_eq "0" "$?" "same-tree promotion succeeds"
assert_contains "$output" "same tree: nothing to promote" "same-tree promotion is skipped"
assert_eq "" "$(cat "$FAKE_LOG" 2>/dev/null || true)" "same-tree promotion does not call GitHub"

printf '0.1.1\n' > VERSION
mkdir dist
printf 'wheel\n' > dist/example.whl
printf 'source\n' > dist/example.tar.gz
"$SCRIPTS/release.sh" tag-release >/dev/null
calls="$(cat "$FAKE_LOG")"
assert_contains "$calls" "release create v0.1.1 dist/example.tar.gz dist/example.whl" "assets are included at release creation"
assert_contains "$calls" "--target" "release targets the checked-out commit"

: > "$FAKE_LOG"
mkdir package
printf 'crate\n' > package/example.crate
RELEASE_ASSET_DIR=package "$SCRIPTS/release.sh" tag-release >/dev/null
assert_contains "$(cat "$FAKE_LOG")" "release create v0.1.1 package/example.crate" "alternate asset directory is used"

: > "$FAKE_LOG"
FAKE_DRAFT=true "$SCRIPTS/release.sh" tag-release >/dev/null
calls="$(cat "$FAKE_LOG")"
assert_contains "$calls" "release upload v0.1.1" "draft release retries asset upload"
assert_contains "$calls" "release edit v0.1.1 --draft=false" "draft release is published after upload"

: > "$FAKE_LOG"
FAKE_DRAFT=false "$SCRIPTS/release.sh" tag-release >/dev/null
assert_eq "" "$(cat "$FAKE_LOG")" "published release is not changed"

finish
