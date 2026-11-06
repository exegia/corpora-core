# Stack-agnostic task runner.
#
# Every dev and CI step is a target here, so anything the pipeline does can be
# reproduced locally. Language-specific work is delegated to scripts/stack.sh,
# which detects Python (uv), Node (TypeScript/React/Expo), Rust (GPUI) and Swift
# (SwiftUI) from the manifests in the repo. Override any task for any stack:
#
#   make test TEST_CMD="pytest -x"        run this instead of the detected command
#   make ci STACKS="python node"          force the stack list
#
# Written for GNU Make 3.81 (macOS default) and newer.

SHELL          := /usr/bin/env bash
.DEFAULT_GOAL  := help

DIST_DIR       ?= dist
TRUNK          ?= main
BUMP           ?= auto
TO             ?= origin/dev
ENV_FILE       ?= .env
export DIST_DIR TRUNK

SCRIPTS        := scripts
STACK          := $(SCRIPTS)/stack.sh
RELEASE        := $(SCRIPTS)/release.sh

##@ Help

.PHONY: help
help: ## Show this help.
	@awk 'BEGIN { FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n" } \
	  /^[a-zA-Z0-9_-]+:.*##/ { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 } \
	  /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)

##@ Dev cycle

.PHONY: doctor
doctor: ## Check the tools this repo's detected stacks need.
	@$(STACK) doctor

.PHONY: setup
setup: install hooks env-init agents-link ## First-time setup: deps, git hooks, .env, commit template, agent skills.
	@git config commit.template .gitmessage
	@echo "Setup done. Next: make dev | make ci"

.PHONY: install
install: ## Install dependencies for every detected stack.
	@$(STACK) run install

.PHONY: hooks
hooks: ## Install pre-commit, commit-msg and pre-push git hooks.
	@if command -v pre-commit >/dev/null 2>&1; then \
	  pre-commit install --install-hooks --hook-type pre-commit --hook-type commit-msg --hook-type pre-push; \
	else \
	  echo "pre-commit not found: install it (uv tool install pre-commit | brew install pre-commit), then run: make hooks"; \
	fi

.PHONY: dev
dev: ## Start the dev server / app (stack default, or DEV_CMD=...).
	@$(STACK) run dev

.PHONY: fmt
fmt: ## Apply formatters and autofixes.
	@$(STACK) run fmt

.PHONY: lint
lint: fmt lint-check ## Apply fixes, then verify.

.PHONY: lint-check
lint-check: ## Verify formatting and lint rules (no changes).
	@$(STACK) run lint

.PHONY: typecheck
typecheck: ## Run type checkers.
	@$(STACK) run typecheck

.PHONY: test
test: ## Run the unit/integration tests (e2e and evals are separate).
	@$(STACK) run test

.PHONY: e2e
e2e: ## Run end-to-end tests.
	@$(STACK) run e2e

.PHONY: eval
eval: ## Run agent/LLM evals (tests/evals or an `eval` script).
	@$(STACK) run eval

.PHONY: build
build: ## Build / compile (verification build, not a release).
	@$(STACK) run build

.PHONY: pack
pack: ## Produce release artifacts in $(DIST_DIR)/ (PACK_CMD=... to override).
	@$(STACK) run pack

.PHONY: selftest
selftest: ## Test this repo's own automation scripts (tests/template).
	@bash tests/template/run.sh

.PHONY: ci
ci: install selftest agents-check lint-check typecheck test build ## Everything CI runs on a pull request.

.PHONY: clean
clean: ## Remove caches and build artifacts (keeps dependencies and lockfiles).
	@rm -rf $(DIST_DIR) build coverage test-results playwright-report .pytest_cache .mypy_cache \
	  .ruff_cache .turbo .next .expo .cache *.egg-info
	@find . -type d -name __pycache__ -not -path './.git/*' -not -path './node_modules/*' -not -path './.venv/*' \
	  -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned caches and build artifacts."

.PHONY: clean-all
clean-all: clean ## Also remove installed dependencies (.venv, node_modules, target, .build).
	@rm -rf .venv node_modules target .build DerivedData
	@echo "Removed installed dependencies. Lockfiles are kept; run: make install"

.PHONY: reset
reset: clean-all install ## Throw away local state and reinstall from the lockfiles.

##@ Secrets and environment

.PHONY: env-init
env-init: ## Create .env from .env.example (chmod 600, never overwrites).
	@$(SCRIPTS)/secrets.sh init

.PHONY: env-check
env-check: ## Diff the keys in .env against .env.example.
	@$(SCRIPTS)/secrets.sh check

.PHONY: secrets-scan
secrets-scan: ## Scan the working tree for credentials (gitleaks).
	@$(SCRIPTS)/secrets.sh scan

.PHONY: secrets-scan-history
secrets-scan-history: ## Scan every commit for credentials (gitleaks).
	@$(SCRIPTS)/secrets.sh scan-history

.PHONY: secrets-push
secrets-push: ## Load ENV_FILE into GitHub secrets (ENVIRONMENT=preview|production optional).
	@ENV_FILE=$(ENV_FILE) $(SCRIPTS)/secrets.sh push

.PHONY: secrets-vars-push
secrets-vars-push: ## Load ENV_FILE into GitHub Actions variables.
	@ENV_FILE=$(ENV_FILE) $(SCRIPTS)/secrets.sh push-vars

.PHONY: secrets-list
secrets-list: ## List secret and variable names on GitHub (never values).
	@$(SCRIPTS)/secrets.sh list

.PHONY: secrets-doctor
secrets-doctor: ## Check the secrets the release automation needs are set.
	@$(SCRIPTS)/secrets.sh doctor

##@ Versioning and release

.PHONY: pkg-version
pkg-version: ## Print the project version from the manifests.
	@$(SCRIPTS)/version.sh get

.PHONY: version-set
version-set: ## Write VERSION=X.Y.Z into every manifest.
	@$(SCRIPTS)/version.sh set "$(VERSION)"

.PHONY: bump-info
bump-info: ## Show the SemVer bump and next version implied by commits since the last tag (TO=origin/dev).
	@echo "latest: $$($(SCRIPTS)/semver.sh latest)"; \
	echo "bump:   $$($(SCRIPTS)/semver.sh bump $(TO))"; \
	echo "next:   v$$($(SCRIPTS)/semver.sh next auto $(TO))"

.PHONY: next-version
next-version: ## Print the next version (BUMP=auto|major|minor|patch, TO=origin/dev).
	@$(SCRIPTS)/semver.sh next $(BUMP) $(TO)

.PHONY: changelog
changelog: ## Print the CHANGELOG section for VERSION=X.Y.Z from TO (default origin/dev).
	@$(SCRIPTS)/changelog.sh section "$(VERSION)" $(TO)

.PHONY: release-notes
release-notes: ## Print "- subject" lines for RANGE (default origin/main..HEAD).
	@$(RELEASE) release-notes

.PHONY: pr-guard
pr-guard: ## Validate a PR's base, branch name and title (env: BASE, HEAD, TITLE).
	@$(SCRIPTS)/pr-guard.sh

.PHONY: bootstrap-lanes
bootstrap-lanes: ## Create origin/dev and origin/next if they do not exist.
	@$(RELEASE) bootstrap-lanes

.PHONY: promote-pr
promote-pr: ## Open or refresh the dev -> next PR (env: VERSION, BUMP).
	@$(RELEASE) promote-pr

.PHONY: cut-release
cut-release: ## Cut or refresh release/v<VERSION> from origin/next (env: VERSION).
	@$(RELEASE) cut-release

.PHONY: release-branch
release-branch: cut-release ## Alias of cut-release.

.PHONY: release-pr
release-pr: ## Open or refresh the draft release PR into main (env: BRANCH).
	@$(RELEASE) release-pr

.PHONY: tag-release
tag-release: ## Tag HEAD as v<project version> and publish the GitHub Release.
	@$(RELEASE) tag-release

.PHONY: delete-branch
delete-branch: ## Delete a remote branch, tolerating one already gone (env: BRANCH).
	@$(RELEASE) delete-branch

.PHONY: sync-lanes
sync-lanes: ## Merge main back into next and dev via PRs.
	@$(RELEASE) sync-lanes

.PHONY: cleanup-cycle
cleanup-cycle: ## Delete remote feature branches merged into dev and stale release/v*.
	@$(RELEASE) cleanup-cycle

.PHONY: cleanup-local
cleanup-local: ## Delete local feature/release branches whose remote is gone.
	@$(RELEASE) cleanup-local

##@ Repository settings (needs gh, admin rights)

.PHONY: repo-bootstrap
repo-bootstrap: ## One-shot: lanes, default branch, settings, labels, rulesets, security features.
	@.github/scripts/bootstrap-repo.sh

.PHONY: settings-apply
settings-apply: ## Apply .github/settings.yml (repo options + security features).
	@.github/scripts/apply-settings.sh settings

.PHONY: labels
labels: ## Create/update the labels in .github/settings.yml.
	@.github/scripts/apply-settings.sh labels

.PHONY: rulesets-diff
rulesets-diff: ## List the rulesets GitHub currently has, by id and name.
	@.github/scripts/apply-rulesets.sh diff

.PHONY: rulesets-apply
rulesets-apply: ## Push .github/rulesets/*.json to GitHub (BYPASS_ACTORS_JSON optional).
	@.github/scripts/apply-rulesets.sh apply

.PHONY: dependabot
dependabot: ## Regenerate .github/dependabot.yml from the detected stacks.
	@$(SCRIPTS)/sync-dependabot.sh

.PHONY: agents-check
agents-check: ## Validate AGENTS.md, CLAUDE.md, copilot instructions and skills.
	@$(SCRIPTS)/agent-assets.sh check

.PHONY: agents-link
agents-link: ## Symlink .claude/skills and .agents/skills to .github/skills (local only).
	@$(SCRIPTS)/agent-assets.sh link
