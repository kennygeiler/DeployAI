#!/usr/bin/env bash
# Pre-write cwd guard. Refuses Write/Edit (and bash output redirects) when
# the target path escapes the agent's assigned worktree.
#
# Activation: self-activates by inspecting `git rev-parse --show-toplevel`.
# If the toplevel lives under `.claude/worktrees/agent-*`, the hook enforces
# confinement to that toplevel. Otherwise (main-thread run inside the main
# repo, or any run outside a git repo) the hook stays permissive. This
# avoids the previous env-var dependency that the Claude Agent SDK's
# `isolation: "worktree"` does not set, which let sub-agents silently
# escape their worktree.
#
# Hook contract: reads tool_use JSON from stdin, writes a decision JSON
# to stdout. Exits 0 always; rejection is via {"decision":"block",...}.
#
# Wire-up in .claude/settings.json under hooks.PreToolUse — see that file.

set -euo pipefail

toplevel="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$toplevel" ]; then
  # Not inside a git repo — nothing to confine to.
  cat <<EOF
{"decision":"allow"}
EOF
  exit 0
fi

case "$toplevel" in
  */.claude/worktrees/agent-*) ;;
  *)
    # Main repo, sibling repo, or unrelated checkout — leave alone.
    cat <<EOF
{"decision":"allow"}
EOF
    exit 0
    ;;
esac

worktree="$toplevel"

payload="$(cat)"
tool="$(printf '%s' "$payload" | jq -r '.tool_name // empty')"

check_path() {
  local target="$1"
  [ -n "$target" ] || return 0
  # Resolve to absolute. Use python rather than realpath so we work even
  # when the file doesn't exist yet (writes create files).
  local resolved
  resolved="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$target")"
  case "$resolved" in
    "$worktree"|"$worktree"/*) return 0 ;;
    *)
      cat <<EOF
{"decision":"block","reason":"refused: $resolved is outside the agent's worktree ($worktree). Edit files via the worktree path. If you meant a different file, fix the path; do not bypass the guard."}
EOF
      return 1
      ;;
  esac
}

case "$tool" in
  Write|Edit|NotebookEdit)
    path="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty')"
    if ! check_path "$path"; then exit 0; fi
    ;;
  Bash)
    cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')"
    # Heuristic: refuse bash commands that pipe into a path outside the
    # worktree. Catches `> /Users/.../file`, `tee /Users/.../file`,
    # `cp x /Users/.../`. Doesn't catch every escape; the harness's own
    # working directory is the primary defense.
    if printf '%s' "$cmd" | grep -qE '(>|tee|cp|mv) +/Users/'; then
      bad="$(printf '%s' "$cmd" | grep -oE '/Users/[^ ]+' | head -1)"
      if [ -n "$bad" ] && ! check_path "$bad"; then exit 0; fi
    fi
    ;;
esac

cat <<EOF
{"decision":"allow"}
EOF
