#!/usr/bin/env bash
# One-shot setup for a repository generated from this template.
#
#   .github/scripts/bootstrap-repo.sh [owner/name]
#
# 1. creates `dev` and `next` from `main` when missing
# 2. makes `dev` the default branch
# 3. applies .github/settings.yml (merge methods, auto-merge, security features)
# 4. creates the labels
# 5. applies the branch and tag rulesets
#
# Idempotent: safe to re-run. Set BYPASS_ACTORS_JSON first (see apply-rulesets.sh)
# so the automation GitHub App can bypass the rulesets. DRY_RUN=1 previews steps 3-5.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=scripts/lib.sh
. "$ROOT/scripts/lib.sh"
cd "$ROOT"

need gh jq
gh auth status >/dev/null 2>&1 || die "not logged in: run gh auth login"
export GH_REPO="${1:-${GH_REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}}"
info "bootstrapping $GH_REPO"

main_sha="$(gh api "repos/$GH_REPO/git/ref/heads/main" --jq .object.sha)" \
  || die "branch 'main' not found; push an initial commit first"

ensure_branch() {
  if gh api "repos/$GH_REPO/git/ref/heads/$1" >/dev/null 2>&1; then skip "branch $1 already exists"
  elif [ "${DRY_RUN:-}" = 1 ]; then info "DRY_RUN create branch $1 from main"
  else
    gh api -X POST "repos/$GH_REPO/git/refs" -f ref="refs/heads/$1" -f sha="$main_sha" >/dev/null
    ok "created branch $1 from main"
  fi
}

ensure_branch dev
ensure_branch next

"$ROOT/.github/scripts/apply-settings.sh" all
"$ROOT/.github/scripts/apply-rulesets.sh" apply

cat <<'EOF'

Still manual (cannot be done safely from a script):
  1. Create a GitHub App (contents: write, pull requests: write, workflows: write), install it on this
     repo, then:  gh secret set AUTOMATION_APP_ID   and   gh secret set AUTOMATION_APP_PRIVATE_KEY
  2. Re-run with BYPASS_ACTORS_JSON set to the App's id (see apply-rulesets.sh).
  3. Optional: gh secret set CLAUDE_CODE_OAUTH_TOKEN  (enables the PR review job)
  4. Check:  make secrets-doctor
EOF
