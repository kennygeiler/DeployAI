# Brief template — copy + fill

cwd CHECK: `cd /Users/kennygeiler/DeployAI && pwd && git rev-parse --show-toplevel && git worktree list`. Confirm worktree-agent-*, NOT ~/DeployAI. The pre-write hook will refuse mis-rooted edits but the check confirms intent.

Read /Users/kennygeiler/DeployAI/AGENTS.md §1-§13 first.

## Slice <ID> — <one-line title>

<2-3 sentence what + why>

## Migration slot (if applicable)

- `services/control-plane/alembic/versions/<YYYYMMDD>_<NNNN>_<name>.py`
- `down_revision` = `<the head on main at branch-cut>`

## Owned files

- <file 1>
- <file 2>
- <test file 1>

## NEVER touch

- <file or pattern>

## Branch + PR

- Branch: `phase-<x>-<id>-<slug>`
- PR title: `<title>`
- PR body per AGENTS.md §8

## Gates

```
<exact commands to run>
```

Return per AGENTS.md §10 in <200 words.
