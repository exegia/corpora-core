---
name: secrets-hygiene
description: Handle .env files, placeholders, gitleaks, push protection, secret rotation and CI secrets safely. Use when adding config or credentials, when the gitleaks hook or Secret Scan fails, a secret leaked, or when pushing secrets to GitHub.
---

# Secrets hygiene

**When to use:** adding env vars or credentials, writing tests/fixtures/examples with tokens, a `gitleaks` hook or `Detect hardcoded secrets` failure, or any suspected leak.

## Rules

- Never commit credentials, tokens, or API keys, including in tests, fixtures, docs, and examples.
- Real values live only in `.env` (gitignored, chmod 600).
- `.env.example` is committed and holds placeholders only, such as `API_KEY=REPLACE_ME`.
- Never paste secrets into issues, PRs, commit messages, logs, chat, or agent prompts.
- Never use `git commit --no-verify` or disable the hook.

## Local workflow

```sh
make env-init           # create .env from .env.example, chmod 600
make env-check          # diff keys between .env and .env.example
make secrets-scan       # gitleaks over the working tree
make secrets-scan-history   # gitleaks over git history
pre-commit install      # hook (also done by make setup)
```

When you add a new variable: add the key to `.env.example` with `REPLACE_ME`, then run `make env-check`.

## When the hook or scan fires

1. Do not bypass. Read which file and rule matched.
2. If it is a real secret: unstage it, move the value to `.env`, reference it via env var.
3. If it was ever pushed or committed: treat as compromised and rotate (below).
4. If it is a false positive: use obviously fake values (`REPLACE_ME`, `example`), or add a narrow allowlist entry to the gitleaks config with a comment. Do not allowlist whole directories.

## Rotation procedure (leak response)

1. Revoke or rotate the credential at the provider first. Removal from git does not make it safe.
2. Update the new value in `.env` and in GitHub secrets.
3. Remove it from history only after rotation (history rewrite on `dev`/`next`/`main` needs the owner).
4. Run `make secrets-scan-history` to confirm.
5. Note the incident in the PR or issue without quoting the value.

## CI secrets and variables

```sh
make secrets-list
make secrets-doctor
make secrets-push ENV_FILE=.env.ci ENVIRONMENT=preview
```

`secrets-push` loads dotenv files with `gh secret set --env-file`. Keep `.env.ci` local and gitignored.

Automation secrets: `AUTOMATION_APP_ID`, `AUTOMATION_APP_PRIVATE_KEY` (GitHub App that opens PRs/tags so downstream workflows trigger), optional `CLAUDE_CODE_OAUTH_TOKEN`, optional publish credentials. Variables (not secrets): `CI_RUNNERS`, `DEPLOY_COMMAND`, `PREVIEW_DEPLOY_COMMAND`, `PUBLISH_PYPI`, `PUBLISH_NPM`, `PUBLISH_CRATES`.

## Pitfalls

- Secrets in tests: use fakes or load from env; never a real token "just for now".
- GitHub push protection blocking a push is the same as a leak: rotate if the value was real.
- Mobile/desktop artifacts (keystores, `google-services.json`, signing keys) are secrets too.
- `echo $SECRET` in a workflow step or Make target can leak into logs; rely on masking and avoid printing.
- Do not store secrets in `.github/workflows/*.md` prompts or agent configs.
