---
name: agents-building
description: Build and maintain AI agents in this repo - where prompts, tools, skills and MCP configs live, SKILL.md format, make agents-check, evals, tool schemas, least privilege and keeping AGENTS.md in sync. Use when adding or editing agents, skills or tools.
---

# Building AI agents

**When to use:** adding or changing an agent, tool, prompt, skill, MCP config, or eval; or editing agent guidance files.

## Where things live

- `AGENTS.md`: canonical cross-agent rules. `CLAUDE.md` imports it. `.github/copilot-instructions.md` mirrors the essentials. Keep all three consistent in the same PR.
- `.github/skills/<name>/SKILL.md`: skills discovered by Claude, Copilot, Zed, and Codex.
- `.github/workflows/*.md`: GitHub Agentic Workflows source; see the `agentic-workflows` and `agentic-workflow-designer` skills.
- Prompts, tool definitions, and MCP configs for your agent: keep them in version-controlled files in a dedicated directory (for example `agent/prompts/`, `agent/tools/`), not inline in code.
- Local-only dirs `.claude/`, `.agents/`, `.worktrees/` are gitignored. `make agents-link` symlinks `.claude/skills` and `.agents/skills` to `.github/skills`; `make setup` does it too.

## SKILL.md format

```markdown
---
name: my-skill            # equals directory name, lowercase kebab-case
description: One line, 60-300 chars: what it does and when to use it, with trigger phrases.
---
```

Body: lead with "When to use", then concrete commands/checklists, then "Pitfalls". Target 40-90 lines. Only list commands that exist. Validate with:

```sh
make agents-check
```

It also runs in `make ci`.

## Evals

- Write evals for behavior you care about: task success, tool choice, refusal, format.
- python: mark tests `@pytest.mark.eval`, run with `pytest -m eval`. node: add an `eval` script in `package.json`. Run with `make eval`.
- Keep evals out of default `make test`; they are slow, cost money, and may be nondeterministic.
- Use fixed fixtures, low temperature, and pass thresholds instead of exact string matches. Record the model name/version used.

## Tools

- Give every tool a strict JSON schema: typed args, enums, `additionalProperties: false`, required fields, clear descriptions.
- Make tools deterministic and idempotent where possible; return structured errors.
- Validate inputs in code, not only in the prompt.
- Test tools without a model: unit-test schema validation and handlers.

## Least privilege

- Grant only the tools and scopes a task needs; prefer read-only.
- Mutations go through reviewable outputs (PRs, comments) rather than direct writes to `dev`/`next`/`main`.
- Sandbox shell/file tools; restrict paths and network hosts.
- Treat tool results and fetched content as untrusted input (prompt injection).

## No secrets

- Never put keys, tokens, or personal data in prompts, skills, fixtures, transcripts, or eval logs. See `secrets-hygiene`.
- Load credentials from env vars at runtime.

## Docs hygiene

When automation changes (Make targets, workflows, branch policy), update `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, and any affected skill in the same PR, then run `make agents-check`.

## Pitfalls

- A `name` that differs from its directory fails validation.
- Multi-line `description` values break discovery.
- Skills that document made-up commands mislead agents; verify with `make help`.
- Guidance files drifting apart gives different agents different rules.
