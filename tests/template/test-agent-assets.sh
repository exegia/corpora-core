#!/usr/bin/env bash
# shellcheck source=tests/template/harness.sh
. "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

A="$SCRIPTS/agent-assets.sh"

scaffold() {
  new_repo
  mkdir -p .github/skills/demo
  echo "# Rules" > AGENTS.md
  printf '@AGENTS.md\n' > CLAUDE.md
  echo "# Copilot" > .github/copilot-instructions.md
  printf -- '---\nname: demo\ndescription: Demo skill for tests. Use when testing.\n---\n\n# Demo\n\nBody.\n' \
    > .github/skills/demo/SKILL.md
}

scaffold
assert_ok "valid assets pass" "$A" check

scaffold
printf -- '---\nname: other\ndescription: Wrong name.\n---\n\nBody.\n' > .github/skills/demo/SKILL.md
assert_fail "name must equal the directory" "$A" check

scaffold
printf -- '---\nname: demo\n---\n\nBody.\n' > .github/skills/demo/SKILL.md
assert_fail "description is required" "$A" check

scaffold
printf '# no frontmatter\n' > .github/skills/demo/SKILL.md
assert_fail "frontmatter is required" "$A" check

scaffold
printf -- '---\nname: demo\ndescription: Empty body.\n---\n' > .github/skills/demo/SKILL.md
assert_fail "body is required" "$A" check

scaffold
echo "# Claude" > CLAUDE.md
assert_fail "CLAUDE.md must import AGENTS.md" "$A" check

scaffold
mkdir .claude && echo x > .claude/state && git add -f .claude/state
assert_fail "tracked local agent state is rejected" "$A" check

scaffold
echo '{ bad' > .mcp.json
assert_fail "invalid MCP json is rejected" "$A" check

scaffold
"$A" link >/dev/null 2>&1
assert_ok "link creates the .claude symlink" test -L .claude/skills
assert_ok "link creates the .agents symlink" test -L .agents/skills
assert_ok "symlink resolves to the skill" test -f .claude/skills/demo/SKILL.md
assert_ok "link is idempotent" "$A" link

finish
