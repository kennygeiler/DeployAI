# AGENTS.md — rules for sub-agents working on DeployAI

You are one of N parallel sub-agents working on the DeployAI roadmap.
Your job is to ship one slice. Stay in your lane. Quality > speed.

This document is **binding**. Your spawn-brief may narrow scope further
but cannot relax these rules. If your brief contradicts this file,
stop and ask the main thread before doing anything.

---

## §1 Read first, in this order

1. **This file (binding).**
2. Root `README.md` + `docs/agent-kenny/INDEX.md` — current product surface and Kenny doc hub.
3. The spawn-brief you were given — slice scope, file ownership,
   migration ID, exact paths.
4. `CLAUDE.md` if present in the repo root.
5. The files you are about to edit, **read in full** before changing
   one line. Match existing patterns.

---

## §2 Scope discipline

- Do exactly the slice in your brief. No "while I'm here" cleanups.
- If you discover a real bug outside scope: flag it in the PR
  description under **Out-of-scope flags**. Do not fix.
- 3+ file edits outside your assigned paths → **STOP and ask main
  thread.** Do not push past your lane silently.
- No new dependencies unless your brief lists them. See §5.
- No new abstractions beyond what the slice requires. Three similar
  lines beats a premature abstraction.

---

## §3 File ownership

Your spawn-brief lists files you own (edit freely) and files siblings
own (read-only). Never edit a sibling's file. Never edit files in §9
without explicit license in your brief.

If a file isn't listed in either set, treat it as **read-only** and
ask before editing.

---

## §4 Migrations (Python / Alembic)

CP migrations live in `services/control-plane/alembic/versions/`.

- Your spawn-brief assigns **one** migration revision ID:
  `YYYYMMDD_NNNN` format.
- `down_revision` = the most recent revision on `main` at the time
  your branch was cut. **Never** chain off a sibling agent's in-flight
  migration — the bundle landing order is not guaranteed.
- One migration per slice. Multi-table change → one revision.
- Run `alembic upgrade head` locally against a fresh testcontainer
  Postgres before commit. CP integration tests do this for you;
  ensure they pass.

---

## §5 Dependencies

Lockfile races are a leading cause of merge conflicts in parallel work.

- **Do NOT run `pnpm add` or `uv add`** unless your spawn-brief
  explicitly lists the new dep with version. Main thread pre-installs
  bundle-wide deps before spawning to avoid lockfile races.
- If you discover mid-task that you need a dep that wasn't listed:
  **STOP and ask** the main thread. Don't add it speculatively.
- Internal `@deployai/*` workspace packages — fine to import without
  asking; they're already wired.

---

## §6 Code conventions

### TypeScript / React
- Strict mode is on. No `any`. No `// @ts-ignore` / `// @ts-expect-error`.
- No `as` casts unless narrowing a `unknown` from a trusted boundary
  (e.g. `JSON.parse`).
- Prefer existing UI primitives (`@/components/ui/*`). ESLint rule
  `no-restricted-syntax` blocks raw `<button>` etc.
- Server vs client components: file naming `Foo.client.tsx` for
  client; server components have no suffix.
- BFF routes are server-only (`route.ts` under `apps/web/src/app/api/`).
- React effects: wrap fetches in `try/catch` so rejections don't
  escape as unhandled (see `EngagementInsights.client.tsx` for the
  pattern). Test teardown can race with effect-fired fetches.
- Don't use `redirect()` from `next/navigation` inside a try/catch —
  it throws an internal NEXT_REDIRECT signal that the catch will
  swallow. Compute the decision inside try; call redirect outside.

### Python (control-plane / cartographer)
- `from __future__ import annotations` in every new module.
- Type-hint every new function. `mypy` must pass with no new errors.
- Use SQLAlchemy 2.x async sessions; FastAPI `Depends` for injection.
- FastAPI Path-param shadowing: a function used as `Depends(...)`
  must not have parameters that collide with the consuming route's
  path params. If you need tenant_id from the request, accept it as
  an arg and have the route pass it in (see
  `resolve_tenant_llm_provider`).
- Alembic migrations: see §4.

### Comments
- **Default to writing no comments.** Only add one when the WHY is
  non-obvious — a hidden constraint, a subtle invariant, a workaround
  for a specific bug.
- Never explain WHAT the code does (well-named identifiers do that).
- Never reference the current task ("added for Sprint 2.2",
  "fixes issue #42"). Those belong in the PR description and rot
  as the codebase evolves.
- Never write multi-paragraph docstrings. One short line max.

### Error handling
- Only validate at system boundaries (user input, external APIs).
  Trust internal code and framework guarantees.
- Don't add fallbacks for scenarios that can't happen.

### Imports
- Match the file's existing order. Don't reorder unrelated imports.
- Group: stdlib / third-party / local (`@/...` or `from
  control_plane...`).

---

## §7 Required local gates before commit

Run these in order. **All must pass** before `git commit`. Don't
commit a red gate to "see what CI thinks."

```bash
# CP gates — run if you touched anything under services/control-plane/
cd services/control-plane
uv run mypy src
uv run ruff check src tests alembic
uv run ruff format --check src tests alembic
uv run pytest tests/unit -x
# Plus the integration files you touched:
uv run pytest -m integration tests/integration/<your-files> -x

# Web gates — run if you touched anything under apps/web/
cd apps/web
pnpm typecheck    # pre-existing src/stories/Foundations/Tokens errors OK; do not introduce NEW errors
pnpm lint
pnpm test

# Root gate — always run, regardless of what you touched
cd <repo-root>
pnpm -w run format:check
```

If any gate fails: fix locally. Do not commit. Do not push.

The root `pnpm -w run format:check` step is the most-missed gate.
It runs `prettier --check .` across the whole monorepo and catches
formatting drift that `turbo lint` does not.

---

## §8 Branch + commit + PR

### Branch naming
`sprint<N>-inc<M>-<short-kebab-slug>`

Examples: `sprint2-inc2-paste-preview`, `sprint3-inc1-citation-drill`.

### Commit message
- Subject ≤ 50 chars, imperative ("Add", "Fix", not "Adding", "Fixed").
- Body wraps at ~72 chars, explains the **why**, not the **what**.
- One commit per slice if you can. Multi-commit OK if each commit is
  a logical unit.
- Never `git push --force` to `main`. Force-push to your own branch
  is fine.

### PR title
`Sprint <N> inc <M>: <slice name>`

### PR body — use this template verbatim

```markdown
## Summary
- <1-3 bullets, what changed and the *reason* for it>

## Test plan
- [x] CP gates green (mypy, ruff check, ruff format --check, pytest)
- [x] Web gates green (typecheck, lint, test)
- [x] `pnpm -w run format:check` green
- [ ] Manual: <what should be eyeballed in a real browser>

## Out-of-scope flags
- <bugs / cleanups you noticed but did NOT fix>
- <or: none>

## Files
- <list of touched paths>
```

---

## §9 NEVER touch without explicit license in your brief

These files have cross-cutting concerns. Modifying them mid-bundle
breaks every sibling agent.

- `apps/web/middleware.ts`
- `packages/authz/` (any file)
- `services/_shared/` (any file)
- `apps/web/src/lib/internal/actor.ts`
- `apps/web/src/lib/internal/deployai-access-jwt.ts`
- Any auth / cookie / JWT / SCIM code
- `pnpm-lock.yaml` (see §5)
- `services/control-plane/alembic/env.py` or `alembic.ini`
- Other agents' assigned files in your bundle (see §3)

If your slice genuinely needs to modify one of these, your spawn-brief
will explicitly grant the license. If it doesn't and you think it
should: **STOP and ask the main thread.**

---

## §10 Return contract

Your final message to the main thread must include:

1. **PR URL.**
2. One-line summary of what you shipped.
3. List of files touched.
4. Out-of-scope flags (bugs / cleanups noticed, NOT fixed).
5. Any deviations from your brief — you SHOULD have asked first;
   surface them explicitly so review catches them.
6. Gates run + their result. ("All gates green" is fine if true.)

Under 200 words. The main thread will read the PR diff itself; your
return message is metadata.

---

## §11 Review pipeline

Every PR goes through:

1. CI (smoke + integration + lint + format + a11y suite) — must be
   green.
2. `cavecrew-reviewer` subagent diff review — one line per finding,
   severity-tagged (Critical / Major / Minor).
3. Main thread spot-check + merge.

If the reviewer finds Critical or Major issues, the PR comes back to
you with the findings. Fix them. Push. Re-review.

Minor issues may be merged at the main thread's discretion or
returned to you for fixup.

---

## §12 Anti-patterns that will get your PR returned

- New dependencies not listed in the brief
- Comments that narrate ("loop through users to build the list")
- Comments referencing tasks/sprints/PRs/issues
- Multi-paragraph docstrings
- New `any` types, `// @ts-ignore`, `// @ts-expect-error`
- `as` casts on non-trusted boundaries
- Raw `<button>` instead of `<Button>`
- `redirect()` inside a `try/catch`
- Fetches in effects without try/catch (causes vitest unhandled
  rejections)
- Backwards-compat shims for code only this PR touched
- "Tier 2 cleanup" or other expansions of your scope
- Editing `pnpm-lock.yaml` outside a brief-approved `pnpm add`
- New migrations that chain off a sibling's revision (see §4)
- Skipping gates ("CI will catch it")
- `--no-verify` on commit or `--no-edit` on rebase

---

## §13 Brief discipline

A subagent spawn-brief gives you what to build, the file list you own,
the migration slot (if any), and the gates. Anything more than that is
process bloat that increases stall risk + dilutes the rules above.

- **Cap: 80 lines.** If a brief is longer, the slice is too big — split
  before spawning.
- **No "go read these 6 files first."** Reference one canonical doc
  (this file, ORCHESTRATOR.md, a design doc) and let the agent fetch
  what it needs. Pre-flight context-reads inflate input tokens + slow
  startup.
- **The cwd CHECK preamble is the only context the brief MUST contain
  verbatim.** Trust the hook (`.claude/hooks/pre_write_cwd_guard.sh`)
  to catch mis-roots; the preamble is the backup.
- **Briefs live in `briefs/`.** Reuse a template instead of hand-rolling.
- **Briefs ban negotiation.** "You may push back on X" → agent burns
  tokens deliberating. "Do X. If X is impossible, return without
  committing and flag in §10 return." → agent ships or stops.
