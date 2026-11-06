#!/usr/bin/env bash
# Apply .github/settings.yml (repository options + labels) and switch on GitHub's
# recommended security features, through the GitHub API.
#
#   .github/scripts/apply-settings.sh settings   repository options + security features
#   .github/scripts/apply-settings.sh labels     create/update labels
#   .github/scripts/apply-settings.sh all        both (default)
#
# Environment: GH_REPO (default: current repo), DRY_RUN=1 to print instead of calling GitHub.
# Needs: gh (admin on the repo), jq, and yq or ruby or python3+PyYAML to read the YAML.
#
# Security features follow GitHub's "Best practices for repositories": Dependabot
# alerts + security updates, secret scanning + push protection, and private
# vulnerability reporting. Features a plan does not offer (for example secret
# scanning on a private repo without GitHub Advanced Security) warn instead of failing.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=scripts/lib.sh
. "$ROOT/scripts/lib.sh"
cd "$ROOT"

SETTINGS=".github/settings.yml"
need gh jq
REPO="${GH_REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"

yaml2json() {
  if have yq && yq --version 2>&1 | grep -qi mikefarah; then yq -o=json '.' "$1"
  elif have yq; then yq '.' "$1"
  elif have ruby; then ruby -ryaml -rjson -e 'puts JSON.generate(YAML.load_file(ARGV[0]))' "$1"
  elif have python3 && python3 -c 'import yaml' 2>/dev/null; then
    python3 -c 'import sys, json, yaml; print(json.dumps(yaml.safe_load(open(sys.argv[1]))))' "$1"
  else die "need yq, ruby or python3 with PyYAML to read $1"; fi
}

# gh_api <method> <path> [json-body]: honours DRY_RUN, returns gh's status.
gh_api() {
  local method="$1" path="$2" body="${3:-}"
  if [ "${DRY_RUN:-}" = 1 ]; then
    info "DRY_RUN $method /repos/$REPO$path ${body:+$body}"; return 0
  fi
  if [ -n "$body" ]; then printf '%s' "$body" | gh api -X "$method" "repos/$REPO$path" --input - >/dev/null
  else gh api -X "$method" "repos/$REPO$path" >/dev/null; fi
}

try() { # try <description> <command...> : warn instead of failing
  local what="$1"; shift
  if "$@" 2>/dev/null; then ok "$what"; else warn "$what: not available for $REPO (plan, permissions or already set)"; fi
}

apply_repository() {
  local json body
  json="$(yaml2json "$SETTINGS")"
  body="$(printf '%s' "$json" | jq -c '.repository // {} | del(.topics)')"
  [ "$body" != "{}" ] || { skip "no repository: section in $SETTINGS"; return 0; }

  # default_branch only works once the branch exists.
  if printf '%s' "$body" | jq -e '.default_branch' >/dev/null; then
    local want; want="$(printf '%s' "$body" | jq -r .default_branch)"
    if ! gh api "repos/$REPO/branches/$want" >/dev/null 2>&1; then
      warn "branch '$want' does not exist yet; skipping default_branch (run make repo-bootstrap)"
      body="$(printf '%s' "$body" | jq -c 'del(.default_branch)')"
    fi
  fi
  try "repository options" gh_api PATCH "" "$body"

  if printf '%s' "$json" | jq -e '.repository.topics' >/dev/null 2>&1; then
    try "topics" gh_api PUT /topics "$(printf '%s' "$json" | jq -c '{names: (.repository.topics | if type == "string" then split(",") | map(gsub("^\\s+|\\s+$"; "")) else . end)}')"
  fi
}

apply_security() {
  try "secret scanning + push protection" gh_api PATCH "" \
    '{"security_and_analysis":{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"}}}'
  try "Dependabot alerts"                 gh_api PUT /vulnerability-alerts
  try "Dependabot security updates"       gh_api PUT /automated-security-fixes
  try "private vulnerability reporting"   gh_api PUT /private-vulnerability-reporting
}

apply_labels() {
  local json n i name color desc
  json="$(yaml2json "$SETTINGS")"
  n="$(printf '%s' "$json" | jq '.labels // [] | length')"
  [ "$n" -gt 0 ] || { skip "no labels: section in $SETTINGS"; return 0; }
  i=0
  while [ "$i" -lt "$n" ]; do
    name="$(printf '%s' "$json" | jq -r ".labels[$i].name")"
    color="$(printf '%s' "$json" | jq -r ".labels[$i].color")"
    desc="$(printf '%s' "$json" | jq -r ".labels[$i].description // \"\"")"
    if [ "${DRY_RUN:-}" = 1 ]; then info "DRY_RUN label '$name' #$color"
    else gh label create "$name" --repo "$REPO" --color "${color#\#}" --description "$desc" --force >/dev/null; fi
    i=$((i + 1))
  done
  ok "$n labels created or updated"
}

case "${1:-all}" in
  settings) apply_repository; apply_security ;;
  labels)   apply_labels ;;
  all)      apply_repository; apply_security; apply_labels ;;
  *)        sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
