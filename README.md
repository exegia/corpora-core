# `repo-template`

GitHub repository template for teams that want a sane default branch model, GitHub Agentic Workflows, Copilot setup, Claude review/chat automation, and template-safe validation before product code exists.

## What this template includes

- **Branch model:** `feature/*` / `bug/*` / `doc/*` / `chore/*` into `dev`, promotion from `dev` to `next`, and release from `next` to `main`
- **Agentic workflows:** issue triage, branch creation, PR review, QA follow-up, promotion flows, and release documentation/tagging
- **GitHub integrations:** Copilot setup workflow plus Claude chat/review workflows
- **Guardrails:** branch-policy automation, protected-branch/ruleset bootstrap assets, and validation workflows that compile `gh-aw` sources

## Use this template

1. Create a new repository from this template.
2. Configure the generated repository's `MAIN_BYPASS_ACTORS_JSON` for the `main` ruleset bypass actors.
3. Run `.github/scripts/apply-branch-guardrails.sh` to create `dev` and `next`, make `dev` the
   default branch, and apply guardrails.
4. Replace the placeholders in `README.md`, `AGENTS.md`, and `CLAUDE.md`.
5. Update `.github/copilot-instructions.md` and the validation workflows to match the real stack.

## Validation commands

These are the only commands this template assumes before you add app code:

| Task | Command |
| --- | --- |
| Compile agentic workflows | `gh aw compile` |
| Compile + lint generated workflows | `gh aw compile --actionlint` |
| Show workflow status | `gh aw status` |

Once a generated repository has its own app or service, replace this section with the real build, lint, and test commands.

## Branching and releases

The template's default lifecycle is documented in:

- `.github/BRANCH-AND-RELEASE-POLICY.md`
- `.github/LIFECYCLE.md`

By default:

1. Lifecycle branches open pull requests into `dev`.
2. Promotion pull requests go from `dev` into `next`.
3. Release pull requests go from `next` into `main`.
4. `main` is read-only except for configured owner and GitHub Actions bypass actors.

## Deployment configuration

`next-preview.yml` and `production-deploy.yml` are intentionally generic. Configure repository
variables `INSTALL_COMMAND`, `TEST_COMMAND`, `BUILD_COMMAND`, `CONTAINER_REGISTRY`,
`CONTAINER_IMAGE`, `CONTAINER_REGISTRY_USERNAME`, `PREVIEW_DEPLOY_COMMAND`, and
`PRODUCTION_DEPLOY_COMMAND` for the generated
application. Use the `preview` and `production` environments to hold the
`CONTAINER_REGISTRY_PASSWORD` and `VERCEL_TOKEN` secrets; no deployment occurs until a command is
configured.

If you change the branch model, update the policy docs, workflow triggers, and agent instruction files together.

## Required GitHub configuration

| Setting / secret | Required | Purpose |
| --- | --- | --- |
| Repository template enabled | yes | Lets teams create new repos from this template |
| Copilot enabled for the repo/org | yes | Powers the agentic `copilot` workflows |
| `CLAUDE_CODE_OAUTH_TOKEN` | yes for Claude workflows | Auth for `anthropics/claude-code-action` |
| Branch protections / rulesets | yes | Prevent deletion and direct mutation of `main`, `dev`, and `next` |

## Repository structure

```text
.
├── .github/
│   ├── workflows/
│   ├── rulesets/
│   ├── scripts/
│   └── copilot-instructions.md
├── AGENTS.md
├── CLAUDE.md
└── README.md
```

## AI collaboration files

- `CLAUDE.md`: repo-specific guidance for Claude-style coding agents
- `AGENTS.md`: cross-agent operating rules for coding agents
- `.github/copilot-instructions.md`: GitHub Copilot repository instructions

Keep those files aligned so local agents, GitHub-hosted agents, and humans follow the same workflow.
