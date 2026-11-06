# Copilot instructions for `repo-template`

## Validation commands

Run commands from the repository root.

| Task | Command |
| --- | --- |
| Compile agentic workflows | `gh aw compile` |
| Compile + lint generated workflows | `gh aw compile --actionlint` |
| Show workflow status | `gh aw status` |

This template does not assume an application stack yet. Once a generated repository has its own codebase, replace these defaults with the real install/build/lint/test commands.

## High-level architecture

This repository is a template for future repositories. The important surfaces are:

- `.github/workflows/*.md`: source files for GitHub Agentic Workflows
- `.github/workflows/*.lock.yml`: compiled workflow artifacts
- plain workflows such as `ci.yml`, `validation.yml`, `pr-base-policy.yml`, and `release-tag.yml`
- starter docs: `README.md`, `AGENTS.md`, `CLAUDE.md`
- repo policy docs: `.github/LIFECYCLE.md`, `.github/BRANCH-AND-RELEASE-POLICY.md`

## Repository-specific conventions

### Workflow conventions

- Treat workflow markdown as the source of truth; recompile after frontmatter changes.
- Keep agentic jobs read-only and use safe outputs for mutations.
- Prefer generic validation that works before downstream code exists.

### Branching conventions

- `dev` is the default branch; lifecycle branches target it.
- Promotion happens from `dev` to `next`.
- Release happens from `next` to `main`.
- `main` is read-only except for explicitly configured owner and GitHub Actions bypass actors.

### Integration conventions

- `copilot-setup-steps.yml` is the bootstrap hook for GitHub Copilot coding agents.
- `claude.yml` and `claude-code-review.yml` depend on `CLAUDE_CODE_OAUTH_TOKEN`.
- Do not commit local-only agent state such as `.claude/`, `.agents/`, or workflow logs.
