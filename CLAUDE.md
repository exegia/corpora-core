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

## Domain agent bundles

Text-Fabric work uses `.github/skills/text-fabric-expert/SKILL.md` and
`agent/text-fabric-expert/SYSTEM.md`. Its source map, MCP configuration generator
and verification instructions live in `agent/text-fabric-expert/README.md`.

## TEI conversion package

`packages/tei-to-tf` provides the TEI acquisition/conversion CLI. Run
`make -C packages/tei-to-tf check build` for its locked Python lint, type, test
and package checks; root stack detection does not discover nested Python projects.
`.github/workflows/tei-converter.yml` runs these checks on relevant PR changes.
See the package README for reading policies, metadata separation and supported boundaries.
