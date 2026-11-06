@AGENTS.md

# Claude-specific notes

`AGENTS.md` above is the shared rulebook; this file only adds what is specific to Claude Code. Do not
duplicate rules here - `make agents-check` fails if the import above is removed.

## Working in this repo

- Prefer `make` targets over raw tool commands; they encode the stack detection CI uses.
- Skills live in `.github/skills/`. Run `make agents-link` once so Claude Code finds them through
  `.claude/skills` (a gitignored symlink). Load the one matching your task before you start.
- Ask for confirmation before anything destructive or shared: force pushes, deleting branches or tags,
  `make rulesets-apply`, `make settings-apply`, `make secrets-push`, `make cut-release`.
- `.claude/`, `.env` and anything under `.worktrees/` are local only. Never stage them.
- When a hook or check fails, fix the cause. Do not skip hooks, do not weaken `.gitleaks.toml`, do not
  edit generated files to make a check pass.

## Finishing a task

1. `make fmt`, then `make ci` (add `make e2e` when behavior visible to users changed).
2. Update `AGENTS.md`, `README.md` and `.github/copilot-instructions.md` if conventions or automation moved.
3. Propose a branch name `<type>/<slug>` and a Conventional Commit PR title; say what you validated.
