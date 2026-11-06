#!/usr/bin/env bash
# Push .github/rulesets/*.json to GitHub (matched by `name`, so re-running updates in place).
#
#   .github/scripts/apply-rulesets.sh diff    list the rulesets GitHub has: id, name, enforcement
#   .github/scripts/apply-rulesets.sh apply   create or update every ruleset file
#
# Environment:
#   GH_REPO              owner/name (default: current repo)
#   BYPASS_ACTORS_JSON   JSON array merged into every ruleset's bypass_actors. GitHub needs numeric
#                        ids, which belong to the generated repository, so they are not committed:
#     BYPASS_ACTORS_JSON='[{"actor_id":123456,"actor_type":"Integration","bypass_mode":"always"}]'
#   (the repository-admin role, actor_id 5, is already in each file)
#   DRY_RUN=1            print the rulesets that would be sent
#
# Add the automation GitHub App's App id before applying, or the App cannot push
# release-branch refreshes or tags (see .github/WORKFLOW.md, "Secrets").

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=scripts/lib.sh
. "$ROOT/scripts/lib.sh"
cd "$ROOT"

need gh jq
REPO="${GH_REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"

cmd_diff() {
  gh api "repos/$REPO/rulesets" --jq '.[] | "\(.id)\t\(.name)\t\(.enforcement)"'
}

cmd_apply() {
  local f name id payload
  for f in .github/rulesets/*.json; do
    name="$(jq -r .name "$f")"
    payload="$(mktemp)"
    if [ -n "${BYPASS_ACTORS_JSON:-}" ]; then
      jq --argjson extra "$BYPASS_ACTORS_JSON" '.bypass_actors = ((.bypass_actors // []) + $extra | unique)' "$f" > "$payload"
    else
      cp "$f" "$payload"
    fi

    if [ "${DRY_RUN:-}" = 1 ]; then
      info "DRY_RUN ruleset '$name' ($(jq -r '.rules | length' "$payload") rules)"; rm -f "$payload"; continue
    fi

    id="$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name==\"$name\") | .id")"
    if [ -n "$id" ]; then
      gh api -X PUT "repos/$REPO/rulesets/$id" --input "$payload" >/dev/null; ok "updated $name"
    else
      gh api -X POST "repos/$REPO/rulesets" --input "$payload" >/dev/null; ok "created $name"
    fi
    rm -f "$payload"
  done
}

case "${1:-}" in
  diff)  cmd_diff ;;
  apply) cmd_apply ;;
  *)     sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; [ -z "${1:-}" ] || exit 2 ;;
esac
