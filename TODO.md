# TODO

Living backlog for this repository. Move items between sections as priorities
change; keep the list short and current.

## Now

### First 30 minutes after using this template

- [ ] Click **Use this template** on GitHub and create the new repository
- [ ] Run `make doctor` and install anything it reports missing
- [ ] Run `make setup` (deps, pre-commit hooks, `.gitmessage` commit template)
- [ ] Run `.github/scripts/bootstrap-repo.sh` to configure repo settings, labels, and branches
- [ ] Set repo secrets `AUTOMATION_APP_ID` and `AUTOMATION_APP_PRIVATE_KEY`
- [ ] Optional: set repo secret `CLAUDE_CODE_OAUTH_TOKEN` for Claude-powered workflows
- [ ] Fill in the `README.md` placeholders
- [ ] Replace the copyright holder in `LICENSE`
- [ ] Replace every `REPLACE_ME` value in `SECURITY.md` and `CODE_OF_CONDUCT.md`
- [ ] Update the security advisory link slug in `SECURITY.md` and `.github/ISSUE_TEMPLATE/config.yml`
- [ ] Edit `.github/CODEOWNERS` (users or a team such as `@exegia/maintainers`)
- [ ] Delete stacks you do not use from `.env.example`
- [ ] Run `make dependabot` to generate Dependabot config for your stacks
- [ ] Enable branch rulesets with `make rulesets-apply`
- [ ] Run `make ci` and confirm it passes on a clean clone

## Next

- [ ] Replace placeholder `make` target implementations with your stack's real commands
- [ ] Add first tests and wire them into `make test` / `make e2e`
- [ ] Update `AGENTS.md` with project-specific architecture and conventions
- [ ] Enable GitHub secret scanning push protection, Dependabot alerts, and CodeQL

## Later

- [ ] Record key decisions as ADRs in `docs/adr/`
- [ ] Trim `.github/skills` to the ones your project uses
- [ ] Add release notes categories or labels you want surfaced in GitHub Releases

## Done

- [x] Repository created from the template
