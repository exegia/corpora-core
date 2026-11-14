#!/usr/bin/env bash
# shellcheck source=tests/template/harness.sh
. "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

new_repo
cp "$ROOT/makefile" makefile
assert_ok "types skips templates without a generator" make types
assert_ok "types-check skips templates without a generator" make types-check
assert_ok "agents-test skips templates without an agent bundle" make agents-test

mkdir -p crates/corpora-typegen bin
touch crates/corpora-typegen/Cargo.toml
cat > bin/cargo <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$TYPEGEN_LOG"
exit "${TYPEGEN_STATUS:-0}"
EOF
chmod +x bin/cargo
export PATH="$PWD/bin:$PATH" TYPEGEN_LOG="$PWD/cargo.log"
assert_ok "types runs configured generator" make types
assert_eq "run --locked -p corpora-typegen" "$(cat cargo.log)" "types generates every target"
: > cargo.log
assert_ok "types-check invokes read-only check" make types-check
assert_eq "run --locked -p corpora-typegen -- --check" "$(cat cargo.log)" "freshness check uses generator"
assert_fail "generation errors fail make" env TYPEGEN_STATUS=1 make types
assert_fail "stale generated models fail make" env TYPEGEN_STATUS=1 make types-check

if command -v python3 >/dev/null 2>&1; then
  mkdir -p agent/text-fabric-expert/tests
  printf 'import unittest\nclass Smoke(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n' > agent/text-fabric-expert/tests/test_smoke.py
  assert_ok "agents-test discovers bundled tests" make agents-test
  printf 'import unittest\nclass Smoke(unittest.TestCase):\n    def test_failure(self):\n        self.fail("expected regression")\n' > agent/text-fabric-expert/tests/test_smoke.py
  assert_fail "agent regressions fail make" make agents-test
fi

prerequisites="$(grep '^ci:' makefile)"
assert_contains "$prerequisites" "types-check" "required CI checks generated models"
assert_contains "$prerequisites" "agents-test" "required CI runs offline agent tests"

for workflow in tei-converter epub-resolver pdf-converter; do
  config="$(cat "$ROOT/.github/workflows/$workflow.yml")"
  assert_contains "$config" "make types-check" "$workflow checks generated freshness"
  assert_contains "$config" "crates/corpora-typegen/**" "$workflow watches generator changes"
  assert_contains "$config" "generated/**" "$workflow watches generated outputs"
  assert_contains "$config" "agent/text-fabric-expert/**" "$workflow watches agent contracts"
done
assert_contains "$(cat "$ROOT/.github/workflows/epub-resolver.yml")" "crates/corpora-core/**" "EPUB checks runtime core contract changes"
assert_contains "$(cat "$ROOT/.github/workflows/packages.yml")" "needs: types" "generated package publishing waits for freshness"
assert_contains "$(cat "$ROOT/.github/workflows/publish.yml")" "make types-check" "release build checks generated freshness"

finish
