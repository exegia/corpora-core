#!/usr/bin/env bash
# Secrets management helpers. Real values live in .env (gitignored); placeholders
# live in .env.example (committed). Nothing here ever prints a secret value.
#
#   scripts/secrets.sh init            create .env from .env.example (chmod 600), never overwrites
#   scripts/secrets.sh check           diff the keys of .env against .env.example
#   scripts/secrets.sh scan            gitleaks over the working tree
#   scripts/secrets.sh scan-history    gitleaks over every commit
#   scripts/secrets.sh scan-staged     gitleaks over staged changes (what the hook runs)
#   scripts/secrets.sh push            load ENV_FILE into GitHub Actions secrets (gh secret set --env-file)
#   scripts/secrets.sh push-vars       load ENV_FILE into GitHub Actions variables
#   scripts/secrets.sh list            names of repo secrets and variables (no values)
#   scripts/secrets.sh doctor          check the secrets this template's automation needs
#
# Environment:
#   ENV_FILE     dotenv file for push / push-vars          (default .env)
#   ENVIRONMENT  GitHub deployment environment, e.g. preview or production (default: repo level)
#   SECRETS_APP  actions | dependabot | codespaces          (default actions)
#   YES=1        skip the confirmation prompt

# shellcheck disable=SC2046,SC2086  # key lists are deliberately word-split into printf args
set -euo pipefail

# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$(repo_root)"

EXAMPLE=".env.example"
ENV_FILE="${ENV_FILE:-.env}"

# Required by the release automation; optional ones only enable extra features.
REQUIRED_SECRETS='AUTOMATION_APP_ID AUTOMATION_APP_PRIVATE_KEY'
OPTIONAL_SECRETS='CLAUDE_CODE_OAUTH_TOKEN'

env_keys() { # env_keys <file>
  sed -nE 's/^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=.*/\2/p' "$1" | sort -u
}

cmd_init() {
  [ -f "$EXAMPLE" ] || die "$EXAMPLE not found"
  if [ -f .env ]; then skip ".env already exists (left untouched)"; return 0; fi
  cp "$EXAMPLE" .env
  chmod 600 .env
  ok "created .env from $EXAMPLE (mode 600). Fill in the real values."
}

cmd_check() {
  [ -f "$EXAMPLE" ] || die "$EXAMPLE not found"
  if [ ! -f .env ]; then
    warn ".env is missing; run: make env-init"
    return 1
  fi
  local missing extra placeholders rc=0
  missing="$(comm -23 <(env_keys "$EXAMPLE") <(env_keys .env))"
  extra="$(comm -13 <(env_keys "$EXAMPLE") <(env_keys .env))"
  placeholders="$(grep -E '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*=(REPLACE_ME)?[[:space:]]*$' .env \
    | sed -E 's/=.*//; s/^[[:space:]]*(export[[:space:]]+)?//' || true)"

  if [ -n "$missing" ]; then
    err "keys in $EXAMPLE but missing from .env:"; printf '  %s\n' $missing >&2; rc=1
  fi
  if [ -n "$extra" ]; then
    warn "keys in .env that $EXAMPLE does not document (add them there, with a placeholder):"
    printf '  %s\n' $extra >&2
  fi
  if [ -n "$placeholders" ]; then
    warn "still placeholders or empty in .env:"; printf '  %s\n' $placeholders >&2
  fi
  [ "$rc" -ne 0 ] || ok ".env matches $EXAMPLE"
  return "$rc"
}

gitleaks_need() { have gitleaks || die "gitleaks not found (brew install gitleaks, or https://github.com/gitleaks/gitleaks)"; }

cmd_scan()         { gitleaks_need; gitleaks dir . --no-banner --redact; }
cmd_scan_history() { gitleaks_need; gitleaks git . --no-banner --redact; }
cmd_scan_staged()  { gitleaks_need; gitleaks git --pre-commit --staged --no-banner --redact --verbose; }

confirm() {
  [ "${YES:-}" = 1 ] && return 0
  [ -t 0 ] || die "refusing to prompt without a terminal; re-run with YES=1"
  local reply; printf '%s [y/N] ' "$1" >&2; read -r reply
  case "$reply" in y|Y|yes|YES) return 0 ;; *) die "aborted" ;; esac
}

push_guard() {
  need gh
  [ -f "$ENV_FILE" ] || die "$ENV_FILE not found"
  if git ls-files --error-unmatch "$ENV_FILE" >/dev/null 2>&1; then
    die "$ENV_FILE is tracked by git; untrack it and rotate anything it contained"
  fi
  if grep -qE '=REPLACE_ME[[:space:]]*$' "$ENV_FILE"; then
    die "$ENV_FILE still contains REPLACE_ME placeholders; fill them in or remove those lines"
  fi
}

push_args() {
  local args=''
  [ -z "${ENVIRONMENT:-}" ] || args="$args --env $ENVIRONMENT"
  [ "$1" = secret ] && [ -n "${SECRETS_APP:-}" ] && args="$args --app $SECRETS_APP"
  printf '%s' "$args"
}

cmd_push() { # cmd_push secret|variable
  local kind="$1" where keys
  push_guard
  where="${ENVIRONMENT:+environment '$ENVIRONMENT' of }$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
  keys="$(env_keys "$ENV_FILE" | tr '\n' ' ')"
  info "will set GitHub Actions ${kind}s on $where from $ENV_FILE:"
  printf '  %s\n' $keys >&2
  confirm "Continue?"
  # shellcheck disable=SC2046
  gh "$kind" set --env-file "$ENV_FILE" $(push_args "$kind")
  ok "${kind}s updated"
}

cmd_list() {
  need gh
  info "secrets";   gh secret list   $( [ -z "${ENVIRONMENT:-}" ] || printf -- '--env %s' "$ENVIRONMENT" )
  info "variables"; gh variable list $( [ -z "${ENVIRONMENT:-}" ] || printf -- '--env %s' "$ENVIRONMENT" )
}

cmd_doctor() {
  need gh
  local have_names n rc=0
  have_names="$(gh secret list --json name --jq '.[].name' 2>/dev/null || true)"
  for n in $REQUIRED_SECRETS; do
    if printf '%s\n' "$have_names" | grep -qx "$n"; then ok "secret $n"
    else err "missing required secret $n (see .github/WORKFLOW.md, 'Secrets')"; rc=1; fi
  done
  for n in $OPTIONAL_SECRETS; do
    if printf '%s\n' "$have_names" | grep -qx "$n"; then ok "secret $n"
    else warn "optional secret $n is not set"; fi
  done
  return "$rc"
}

main() {
  local cmd="${1:-}"; [ "$#" -gt 0 ] && shift
  case "$cmd" in
    init)         cmd_init ;;
    check)        cmd_check ;;
    scan)         cmd_scan ;;
    scan-history) cmd_scan_history ;;
    scan-staged)  cmd_scan_staged ;;
    push)         cmd_push secret ;;
    push-vars)    cmd_push variable ;;
    list)         cmd_list ;;
    doctor)       cmd_doctor ;;
    *) sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; [ -z "$cmd" ] || exit 2 ;;
  esac
}

main "$@"
