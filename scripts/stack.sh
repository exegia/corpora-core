#!/usr/bin/env bash
# Stack-aware task runner. Every `make` dev/CI target funnels through here, so a
# generated repository gets the right commands for Python, Node (TypeScript,
# React, Expo), Rust (GPUI) and Swift (SwiftUI) without editing the Makefile.
#
#   scripts/stack.sh list                 build stacks detected here
#   scripts/stack.sh tags                 stacks plus flavors (typescript react expo gpui)
#   scripts/stack.sh runners              JSON array of GitHub runner labels for pull requests
#   scripts/stack.sh matrix-runners       JSON array of runners for the wider post-merge matrix
#   scripts/stack.sh codeql               JSON include-list of CodeQL languages
#   scripts/stack.sh doctor               verify the tools the detected stacks need
#   scripts/stack.sh run <task> [stack]   install fmt lint typecheck test e2e eval build pack dev
#
# Overrides (any task, runs once instead of the detected commands):
#   TEST_CMD="make -C app test" scripts/stack.sh run test
# Force the stack list:  STACKS="python node"
#
# With nothing detected every task is a clean no-op, so the template stays
# green before the first line of product code exists.

# shellcheck disable=SC2046  # $(rust_locked) must word-split to nothing when there is no Cargo.lock
set -euo pipefail

# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$(repo_root)"

# ── Python (uv) ──────────────────────────────────────────────────────────────

py_configured() { # py_configured <tool> -> tool is a declared dependency or has a config file
  grep -qiE "(^|[^a-z0-9_-])$1([^a-z0-9_-]|$)" pyproject.toml 2>/dev/null || [ -f "$1.toml" ] || [ -f ".$1.toml" ]
}
py_run() { if [ -f pyproject.toml ]; then uv run "$@"; else "$@"; fi; }

task_python_install() {
  if [ -f pyproject.toml ]; then
    need uv
    if in_ci && [ -f uv.lock ]; then uv sync --locked; else uv sync; fi
  elif [ -f requirements.txt ]; then
    python3 -m pip install -r requirements.txt
  fi
}
task_python_fmt() {
  py_configured ruff || { skip "ruff not configured"; return 0; }
  py_run ruff check --fix . && py_run ruff format .
}
task_python_lint() {
  py_configured ruff || { skip "ruff not configured"; return 0; }
  py_run ruff check . && py_run ruff format --check .
}
task_python_typecheck() {
  if   py_configured mypy;    then py_run mypy .
  elif py_configured pyright; then py_run pyright
  elif py_configured ty;      then py_run ty check
  else skip "no type checker configured (mypy, pyright or ty)"; fi
}
task_python_test() {
  if py_configured pytest || [ -d tests ]; then
    # e2e and eval suites are opt-in (own targets), never part of the fast loop.
    # pytest exits 5 when nothing was collected, which is fine for a fresh repo.
    local rc=0
    py_run pytest -m "not e2e and not eval" || rc=$?
    [ "$rc" -eq 5 ] && return 0
    return "$rc"
  else skip "no pytest configuration or tests/ directory"; fi
}
task_python_e2e() {
  if [ -d tests/e2e ]; then py_run pytest tests/e2e
  else skip "no tests/e2e directory"; fi
}
task_python_eval() {
  if [ -d tests/evals ]; then py_run pytest tests/evals
  else skip "no tests/evals directory"; fi
}
task_python_build() { task_python_pack; }
task_python_pack() {
  grep -q '^\[build-system\]' pyproject.toml 2>/dev/null || { skip "no [build-system] in pyproject.toml"; return 0; }
  need uv
  uv build --out-dir "$DIST_DIR"
}
task_python_dev() { skip "set DEV_CMD to start a dev process (e.g. DEV_CMD='uv run fastapi dev')"; }

# ── Node: TypeScript, React, Expo ────────────────────────────────────────────

node_run_script() { # node_run_script <script> [args] -> run via the detected package manager
  local pm; pm="$(node_pm)"
  case "$pm" in
    npm)  npm run "$@" ;;
    yarn) yarn run "$@" ;;
    *)    "$pm" run "$@" ;;
  esac
}
node_exec() {
  case "$(node_pm)" in
    bun)  bunx "$@" ;;
    pnpm) pnpm exec "$@" ;;
    yarn) yarn "$@" ;;
    *)    npx --no-install "$@" ;;
  esac
}
node_script_real() { # a real script, not npm's "no test specified" stub
  local body; body="$(pkg_script "$1")"
  [ -n "$body" ] && ! printf '%s' "$body" | grep -q 'no test specified'
}
node_first_script() { local s; for s in "$@"; do node_script_real "$s" && { echo "$s"; return 0; }; done; return 1; }

task_node_install() {
  need node
  case "$(node_pm)" in
    bun)  need bun;  if in_ci; then bun install --frozen-lockfile; else bun install; fi ;;
    pnpm) need pnpm; if in_ci; then pnpm install --frozen-lockfile; else pnpm install; fi ;;
    yarn) need yarn; if in_ci; then yarn install --immutable; else yarn install; fi ;;
    *)    if [ -f package-lock.json ]; then npm ci; else npm install; fi ;;
  esac
}
task_node_fmt() {
  local s
  if s="$(node_first_script format fmt lint:fix)"; then node_run_script "$s"
  else skip "no format/fmt/lint:fix script in package.json"; fi
}
task_node_lint() {
  if node_script_real lint; then node_run_script lint
  else skip "no lint script in package.json"; fi
}
task_node_typecheck() {
  local s
  if s="$(node_first_script typecheck type-check tsc)"; then node_run_script "$s"
  elif [ -f tsconfig.json ] && [ -x node_modules/.bin/tsc ]; then node_exec tsc --noEmit
  else skip "no typecheck script and no local TypeScript"; fi
}
task_node_test() {
  if node_script_real test; then node_run_script test
  else skip "no test script in package.json"; fi
}
task_node_e2e() {
  local s
  if s="$(node_first_script test:e2e e2e)"; then node_run_script "$s"
  elif [ -d .maestro ] && have maestro; then maestro test .maestro
  elif ls playwright.config.* >/dev/null 2>&1; then node_exec playwright test
  else skip "no test:e2e script, Maestro flows (.maestro/) or Playwright config"; fi
}
task_node_eval() {
  if node_script_real eval; then node_run_script eval
  else skip "no eval script in package.json"; fi
}
task_node_build() {
  if node_script_real build; then node_run_script build
  else skip "no build script in package.json"; fi
}
task_node_pack() {
  mkdir -p "$DIST_DIR"
  if node_script_real pack; then node_run_script pack
  elif pkg_has_dep expo; then node_exec expo export --output-dir "$DIST_DIR"
  elif [ "$(jq -r '.private // false' package.json)" = "true" ]; then
    task_node_build
  else
    npm pack --pack-destination "$DIST_DIR"
  fi
}
task_node_dev() {
  local s
  if s="$(node_first_script dev start)"; then node_run_script "$s"
  else skip "no dev/start script in package.json"; fi
}

# ── Rust (incl. GPUI) ────────────────────────────────────────────────────────

rust_locked() { if [ -f Cargo.lock ]; then echo --locked; fi; }

task_rust_install() { need cargo; cargo fetch $(rust_locked); }
task_rust_fmt()     { need cargo; cargo fmt --all; }
task_rust_lint() {
  need cargo
  cargo fmt --all -- --check
  cargo clippy --workspace --all-targets --all-features $(rust_locked) -- -D warnings
}
task_rust_typecheck() { skip "covered by clippy in lint"; }
task_rust_test() {
  need cargo
  if cargo nextest --version >/dev/null 2>&1; then
    cargo nextest run --workspace --all-features $(rust_locked)
    cargo test --workspace --all-features --doc $(rust_locked)
  else
    cargo test --workspace --all-features $(rust_locked)
  fi
}
task_rust_e2e() {
  need cargo
  if [ -f tests/e2e.rs ] || [ -f tests/e2e/main.rs ]; then
    cargo test --all-features --test e2e $(rust_locked)
  else skip "no tests/e2e.rs or tests/e2e/main.rs"; fi
}
task_rust_build() { need cargo; cargo build --workspace --all-targets $(rust_locked); }
task_rust_pack() {
  need cargo
  cargo build --workspace --release $(rust_locked)
  info "release binaries are in target/release; set PACK_CMD to bundle them into $DIST_DIR (e.g. cargo-bundle)"
}
task_rust_dev() { need cargo; cargo run; }

# ── Swift (SwiftPM or Xcode project; SwiftUI) ────────────────────────────────

swift_mode() { # package | xcode
  if _has_glob '*.xcworkspace' || _has_glob '*.xcodeproj'; then echo xcode
  else echo package; fi
}
xcode_container() {
  local f
  for f in *.xcworkspace; do [ -e "$f" ] && { echo "-workspace $f"; return; }; done
  for f in *.xcodeproj;   do [ -e "$f" ] && { echo "-project $f";   return; }; done
}
xcode_scheme() {
  if [ -n "${XCODE_SCHEME:-}" ]; then echo "$XCODE_SCHEME"; return; fi
  have jq || die "set XCODE_SCHEME (jq is needed to auto-detect it)"
  # shellcheck disable=SC2046
  xcodebuild -list -json $(xcode_container) 2>/dev/null \
    | jq -r '(.workspace.schemes // .project.schemes // [])[0] // empty'
}
xcode() { # xcode <action> [extra args]
  local action="$1"; shift
  local scheme; scheme="$(xcode_scheme)"
  [ -n "$scheme" ] || die "no Xcode scheme found; set XCODE_SCHEME"
  # shellcheck disable=SC2046
  xcodebuild $(xcode_container) -scheme "$scheme" \
    -destination "${XCODE_DESTINATION:-platform=macOS}" "$action" "$@"
}

task_swift_install() {
  need swift
  if [ "$(swift_mode)" = package ]; then swift package resolve
  else xcode -resolvePackageDependencies >/dev/null; fi
}
task_swift_fmt() {
  if swift format --version >/dev/null 2>&1 && [ -d Sources ]; then
    swift format --in-place --recursive Sources $( [ -d Tests ] && echo Tests )
  else skip "swift format unavailable or no Sources/ directory"; fi
}
task_swift_lint() {
  if have swiftlint; then swiftlint --strict
  else skip "swiftlint not installed (brew install swiftlint)"; fi
}
task_swift_typecheck() { skip "covered by build"; }
task_swift_test() {
  need swift
  if [ "$(swift_mode)" = package ]; then swift test; else xcode test; fi
}
task_swift_e2e() {
  if [ -z "${XCODE_UITEST_TARGET:-}" ]; then skip "set XCODE_UITEST_TARGET to run UI tests"; return 0; fi
  xcode test "-only-testing:$XCODE_UITEST_TARGET"
}
task_swift_build() {
  need swift
  if [ "$(swift_mode)" = package ]; then swift build; else xcode build; fi
}
task_swift_pack() {
  need swift
  if [ "$(swift_mode)" = package ]; then swift build -c release
  else xcode archive -archivePath "$DIST_DIR/$(xcode_scheme).xcarchive"; fi
}
task_swift_dev() { skip "open the project in Xcode, or set DEV_CMD"; }

# ── Dispatcher ───────────────────────────────────────────────────────────────

TASKS='install fmt lint typecheck test e2e eval build pack dev'

override_for() { # override_for <task> -> value of <TASK>_CMD (empty when unset)
  local var; var="$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')_CMD"
  eval "printf '%s' \"\${$var:-}\""
}

run_task() {
  local task="$1" only="${2:-}" override stack rc=0 ran=0
  case " $TASKS " in *" $task "*) ;; *) die "unknown task '$task' (one of: $TASKS)" ;; esac

  override="$(override_for "$task")"
  if [ -n "$override" ]; then
    group_start "$task (override)"
    bash -o pipefail -c "$override" || rc=$?
    group_end
    return "$rc"
  fi

  for stack in $(detect_stacks); do
    [ -z "$only" ] || [ "$only" = "$stack" ] || continue
    if ! declare -F "task_${stack}_${task}" >/dev/null; then
      skip "$task: nothing defined for $stack"; continue
    fi
    ran=1
    group_start "$task ($stack)"
    if ! "task_${stack}_${task}"; then
      err "$task failed for $stack"
      rc=1
    fi
    group_end
  done

  if [ "$ran" -eq 0 ] && [ -z "$(detect_stacks)" ]; then
    skip "$task: no stack detected (add pyproject.toml, package.json, Cargo.toml or Package.swift, or set STACKS / $(printf '%s' "$task" | tr '[:lower:]' '[:upper:]')_CMD)"
  fi

  # `make dev` may be a pure override with no detected stack.
  return "$rc"
}

# ── CI helpers ───────────────────────────────────────────────────────────────

cmd_runners() {
  if [ -n "${CI_RUNNERS:-}" ]; then printf '%s\n' "$CI_RUNNERS"; return; fi
  if stack_active swift || tag_active gpui; then echo '["macos-latest"]'
  else echo '["ubuntu-latest"]'; fi
}

# Wider OS coverage for pushes to next and the nightly run.
cmd_matrix_runners() {
  if [ -n "${MATRIX_RUNNERS:-}" ]; then printf '%s\n' "$MATRIX_RUNNERS"; return; fi
  if stack_active swift; then echo '["macos-latest"]'
  else echo '["ubuntu-latest","macos-latest"]'; fi
}

cmd_codeql() { # JSON array of {language, runner, build-mode}
  local out='' sep='' s
  add() { out="$out$sep{\"language\":\"$1\",\"runner\":\"$2\",\"build-mode\":\"$3\"}"; sep=','; }
  for s in $(detect_stacks); do
    case "$s" in
      python) add python ubuntu-latest none ;;
      node)   add javascript-typescript ubuntu-latest none ;;
      rust)   add rust ubuntu-latest none ;;
      swift)  add swift macos-latest autobuild ;;
    esac
  done
  [ -d .github/workflows ] && add actions ubuntu-latest none
  printf '[%s]\n' "$out"
}

cmd_doctor() {
  local missing=0 s t
  chk() { # chk <tool> <why> [required]
    if have "$1"; then ok "$1"
    elif [ "${3:-required}" = optional ]; then warn "$1 not found ($2)"
    else err "$1 not found ($2)"; missing=1; fi
  }
  info "base tools"
  chk git "version control"; chk make "task runner"; chk jq "package.json/JSON handling"
  chk gh "release + repo automation" optional
  chk gitleaks "secret scanning (brew install gitleaks)" optional
  chk pre-commit "git hooks (uv tool install pre-commit)" optional
  chk shellcheck "shell lint (brew install shellcheck)" optional
  chk actionlint "workflow lint (brew install actionlint)" optional

  s="$(detect_tags | tr '\n' ' ')"
  info "detected stacks: ${s:-none}"
  for t in $(detect_stacks); do
    case "$t" in
      python) chk uv "Python toolchain (https://docs.astral.sh/uv/)" ;;
      node)   chk node "Node runtime"; chk "$(node_pm)" "package manager (from lockfile)" ;;
      rust)   chk cargo "Rust toolchain (https://rustup.rs)"; chk rustfmt "cargo fmt"; chk cargo-clippy "cargo clippy" ;;
      swift)  chk swift "Swift toolchain (Xcode)"; chk xcodebuild "Xcode CLI tools" optional
              chk swiftlint "Swift lint (brew install swiftlint)" optional ;;
    esac
  done
  if tag_active expo; then chk maestro "Expo e2e flows (https://maestro.mobile.dev)" optional; fi
  if tag_active gpui && [ "$(uname -s)" = Linux ]; then
    info "GPUI on Linux also needs system libs (see .github/actions/setup/action.yml)"
  fi
  return "$missing"
}

main() {
  local cmd="${1:-}"; [ "$#" -gt 0 ] && shift
  case "$cmd" in
    list)    detect_stacks ;;
    tags)    detect_tags ;;
    runners) cmd_runners ;;
    matrix-runners) cmd_matrix_runners ;;
    codeql)  cmd_codeql ;;
    doctor)  cmd_doctor ;;
    run)     [ "$#" -ge 1 ] || die "usage: stack.sh run <task> [stack]"; run_task "$@" ;;
    *)       sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; [ -z "$cmd" ] || exit 2 ;;
  esac
}

main "$@"
