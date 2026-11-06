#!/usr/bin/env bash
# Keep AI-agent assets healthy and discoverable.
#
#   scripts/agent-assets.sh check   validate AGENTS.md, CLAUDE.md, copilot instructions, skills, MCP config
#   scripts/agent-assets.sh link    symlink .claude/skills and .agents/skills to .github/skills (local only)
#
# .github/skills is the single committed source of truth. .claude/ and .agents/
# are gitignored, local-only views of it so Claude Code, Codex and Zed find the
# same skills Copilot reads.

set -euo pipefail

# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$(repo_root)"

SKILLS_DIR=".github/skills"
bad=0
fail() { err "$*"; bad=1; }

frontmatter() { # frontmatter <file> -> lines between the first two --- fences
  awk 'NR == 1 && $0 != "---" { exit } NR == 1 { next } /^---[[:space:]]*$/ { exit } { print }' "$1"
}

check_skill() {
  local dir="$1" file name desc fm
  file="$dir/SKILL.md"
  [ -f "$file" ] || { fail "$dir has no SKILL.md"; return; }
  [ "$(sed -n '1p' "$file")" = "---" ] || { fail "$file must start with a --- frontmatter fence"; return; }
  fm="$(frontmatter "$file")"
  [ -n "$fm" ] || { fail "$file has empty or unterminated frontmatter"; return; }

  name="$(printf '%s\n' "$fm" | sed -nE 's/^name:[[:space:]]*"?([^"]*)"?[[:space:]]*$/\1/p' | sed -n '1p')"
  desc="$(printf '%s\n' "$fm" | sed -nE 's/^description:[[:space:]]*(.*)$/\1/p' | sed -n '1p')"

  [ -n "$name" ] || fail "$file: missing 'name:'"
  [ -z "$name" ] || [ "$name" = "$(basename "$dir")" ] || fail "$file: name '$name' must equal directory '$(basename "$dir")'"
  printf '%s' "${name:-x}" | grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$' || fail "$file: name must be lowercase kebab-case"
  [ -n "$desc" ] || fail "$file: missing single-line 'description:'"
  [ "${#desc}" -le 1024 ] || fail "$file: description is longer than 1024 characters"
  [ "$(awk 'f && NF { n++ } /^---[[:space:]]*$/ && NR > 1 { f = 1 } END { print n + 0 }' "$file")" -gt 0 ] || fail "$file: empty body"
}

cmd_check() {
  local f d n=0
  for f in AGENTS.md CLAUDE.md .github/copilot-instructions.md; do
    [ -s "$f" ] || fail "$f is missing or empty"
  done
  if [ -s CLAUDE.md ] && ! grep -q '@AGENTS.md' CLAUDE.md; then
    fail "CLAUDE.md must import @AGENTS.md so the two files cannot drift"
  fi

  if [ -d "$SKILLS_DIR" ]; then
    for d in "$SKILLS_DIR"/*/; do
      [ -d "$d" ] || continue
      check_skill "${d%/}"; n=$((n + 1))
    done
  fi

  for f in .mcp.json .github/mcp.json; do
    if [ -f "$f" ] && have jq && ! jq empty "$f" >/dev/null 2>&1; then fail "$f is not valid JSON"; fi
  done

  if [ -n "$(git ls-files .claude .agents .worktrees 2>/dev/null)" ]; then
    fail "local-only agent state is tracked by git (.claude/, .agents/ or .worktrees/); untrack it"
  fi

  if [ "$bad" -eq 0 ]; then ok "agent assets valid ($n skills)"; fi
  return "$bad"
}

link_skills() { # link_skills <dir>
  local parent="$1" target="$1/skills"
  mkdir -p "$parent"
  if [ -L "$target" ]; then skip "$target is already a symlink"
  elif [ -e "$target" ]; then warn "$target exists and is not a symlink; leaving it alone"
  else ln -s "../$SKILLS_DIR" "$target"; ok "$target -> ../$SKILLS_DIR"; fi
}

cmd_link() {
  [ -d "$SKILLS_DIR" ] || die "$SKILLS_DIR not found"
  link_skills .claude
  link_skills .agents
}

main() {
  local cmd="${1:-}"; [ "$#" -gt 0 ] && shift
  case "$cmd" in
    check) cmd_check ;;
    link)  cmd_link ;;
    *) sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; [ -z "$cmd" ] || exit 2 ;;
  esac
}

main "$@"
