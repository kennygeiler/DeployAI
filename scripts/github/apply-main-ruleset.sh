#!/usr/bin/env bash
# Apply the main branch ruleset via GitHub API (requires: gh auth login, admin on repo)
set -euo pipefail
REPO_SLUG="${1:-${GITHUB_REPOSITORY:-}}"
if [[ -z "$REPO_SLUG" ]]; then
  echo "Usage: GITHUB_OWNER/REPO $0   or   export GITHUB_REPOSITORY=owner/repo" >&2
  exit 1
fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec gh api --method POST "repos/${REPO_SLUG}/rulesets" --input "${ROOT}/scripts/github/main-ruleset.json"
