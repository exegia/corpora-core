#!/usr/bin/env bash
# shellcheck source=tests/template/harness.sh
. "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

V="$SCRIPTS/version.sh"

# ── VERSION file fallback ──
new_repo
echo "0.0.0" > VERSION
assert_eq "0.0.0" "$("$V" get)" "VERSION is the fallback"
"$V" set 0.1.0 >/dev/null 2>&1
assert_eq "0.1.0" "$(cat VERSION)" "set rewrites VERSION"

# ── Python: only [project] changes, never decoys in other tables ──
new_repo
cat > pyproject.toml <<'EOF'
[build-system]
requires = ["hatchling"]

[project]
name = "demo"
version = "0.1.0"
dependencies = ["x"]

[tool.other]
version = "9.9.9"
EOF
assert_eq "0.1.0" "$("$V" get)" "reads [project] version"
"$V" set 1.4.0 >/dev/null 2>&1
assert_eq "1.4.0" "$("$V" get)" "set updates [project]"
assert_contains "$(cat pyproject.toml)" 'version = "9.9.9"' "decoy table untouched"

# ── Cargo: [package] only, not dependency tables ──
new_repo
cat > Cargo.toml <<'EOF'
[package]
name = "demo"
version = "0.2.0"
edition = "2021"

[dependencies.foo]
version = "1.0.0"
EOF
assert_eq "0.2.0" "$("$V" get)" "reads [package] version"
"$V" set 0.3.0 >/dev/null 2>&1
assert_eq "0.3.0" "$("$V" get)" "set updates [package]"
assert_contains "$(cat Cargo.toml)" 'version = "1.0.0"' "dependency version untouched"

# ── Node + Expo: package.json and app.json move together ──
new_repo
cat > package.json <<'EOF'
{
  "name": "demo",
  "version": "0.5.0",
  "dependencies": { "left-pad": "1.3.0" }
}
EOF
cat > app.json <<'EOF'
{ "expo": { "name": "demo", "version": "0.5.0" } }
EOF
assert_eq "0.5.0" "$("$V" get)" "reads package.json"
"$V" set 0.6.0 >/dev/null 2>&1
assert_eq "0.6.0" "$(jq -r .version package.json)" "package.json updated"
assert_eq "0.6.0" "$(jq -r .expo.version app.json)" "app.json updated"
assert_eq "1.3.0" "$(jq -r '.dependencies["left-pad"]' package.json)" "dependencies untouched"
assert_ok "manifests agree" "$V" check

# ── disagreement is caught ──
jq '.version = "9.0.0"' package.json > p.tmp && mv p.tmp package.json
assert_fail "check fails when manifests disagree" "$V" check

# ── release branch must match ──
new_repo
echo "1.2.3" > VERSION
assert_ok "matching release branch" "$V" branch-matches release/v1.2.3
assert_fail "mismatched release branch" "$V" branch-matches release/v1.2.4

# ── input validation ──
assert_fail "set rejects non-semver" "$V" set 1.2
assert_fail "get fails with no manifest" bash -c "cd \"$(mktemp -d)\" && git init -q && '$V' get"

finish
