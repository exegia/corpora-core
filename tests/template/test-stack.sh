#!/usr/bin/env bash
# shellcheck source=tests/template/harness.sh
. "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

K="$SCRIPTS/stack.sh"

# ── nothing detected: every task is a clean no-op ──
new_repo
assert_eq "" "$("$K" list)" "empty repo has no stacks"
assert_eq '["ubuntu-latest"]' "$("$K" runners)" "default runner"
for task in install fmt lint typecheck test e2e eval build pack dev; do
  assert_ok "$task is a no-op without a stack" "$K" run "$task"
done
assert_fail "unknown task" "$K" run frobnicate

# ── overrides ──
assert_fail "override command failure propagates" env TEST_CMD="exit 3" "$K" run test
assert_ok   "override command runs" env TEST_CMD="true" "$K" run test
assert_eq "python node" "$(STACKS='python node' "$K" list | tr '\n' ' ' | sed 's/ $//')" "STACKS forces the list"

# ── Python ──
new_repo
printf '[project]\nname = "x"\nversion = "0.1.0"\n' > pyproject.toml
assert_eq "python" "$("$K" list)" "pyproject.toml means python"
assert_eq '["ubuntu-latest"]' "$("$K" runners)" "python runs on ubuntu"
assert_contains "$("$K" codeql)" '"language":"python"' "codeql knows python"

# ── Node flavors ──
new_repo
cat > package.json <<'EOF'
{ "name": "x", "version": "0.1.0",
  "dependencies": { "react": "19.0.0", "expo": "54.0.0" },
  "devDependencies": { "typescript": "5.0.0" },
  "scripts": { "lint": "echo linting-ok", "test": "echo \"Error: no test specified\" && exit 1" } }
EOF
echo '{}' > tsconfig.json
assert_eq "node" "$("$K" list)" "package.json means node"
tags="$("$K" tags | tr '\n' ' ')"
assert_contains "$tags" "typescript" "typescript flavor"
assert_contains "$tags" "react" "react flavor"
assert_contains "$tags" "expo" "expo flavor"
assert_eq "npm" "$(. "$SCRIPTS/lib.sh"; node_pm)" "npm by default"
touch pnpm-lock.yaml
assert_eq "pnpm" "$(. "$SCRIPTS/lib.sh"; node_pm)" "pnpm from lockfile"
rm pnpm-lock.yaml
if command -v npm >/dev/null 2>&1; then
  out="$("$K" run lint 2>&1)"
  assert_contains "$out" "linting-ok" "runs the package.json lint script"
  assert_ok "npm's default test stub is skipped" "$K" run test
fi

# ── Rust / GPUI ──
new_repo
printf '[package]\nname = "x"\nversion = "0.1.0"\n\n[dependencies]\ngpui = { git = "https://github.com/zed-industries/zed" }\n' > Cargo.toml
assert_eq "rust" "$("$K" list)" "Cargo.toml means rust"
assert_contains "$("$K" tags | tr '\n' ' ')" "gpui" "gpui flavor"
assert_eq '["macos-latest"]' "$("$K" runners)" "gpui prefers macOS"

new_repo
printf '[package]\nname = "x"\nversion = "0.1.0"\n' > Cargo.toml
assert_eq '["ubuntu-latest"]' "$("$K" runners)" "plain rust runs on ubuntu"

# ── Swift ──
new_repo
echo '// swift-tools-version: 5.9' > Package.swift
assert_eq "swift" "$("$K" list)" "Package.swift means swift"
assert_eq '["macos-latest"]' "$("$K" runners)" "swift needs macOS"
assert_eq '["macos-latest"]' "$("$K" matrix-runners)" "swift matrix is macOS only"

# ── runner variable wins ──
assert_eq '["self-hosted"]' "$(CI_RUNNERS='["self-hosted"]' "$K" runners)" "CI_RUNNERS override"

finish
