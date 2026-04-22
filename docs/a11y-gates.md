# Accessibility CI gate stack

> **Story 1.6** landed a four-layer accessibility gate that runs on every PR
> and every push to `main`. All four layers are **CI-blocking** — if any one
> of them reports a violation, the PR cannot merge. This is intentional: we
> are building a government-facing product (StateRAMP, FedRAMP, Section 508),
> and shipping a regression is a compliance incident, not a usability bug.

---

## The four gates at a glance

| Layer | Tool(s) | What it catches | Run time (CI) | Owner file |
|---|---|---|---|---|
| 1. **Static lint** | `eslint-plugin-jsx-a11y` @ `error` | Missing `alt`, empty `aria-label`, illegal ARIA, non-interactive events, unresolved roles | ~1 min | `apps/web/eslint.config.mjs` |
| 2. **Per-story axe** | `@storybook/test-runner` + `@axe-core/playwright` | Component-level WCAG violations caught before composition | ~3 min | `apps/web/.storybook/test-runner.ts` |
| 3. **E2E axe** | `@playwright/test` + `@axe-core/playwright` | Full-page WCAG on production build, keyboard entry smoke | ~3 min | `apps/web/tests/e2e/*.a11y.spec.ts` |
| 4. **axe + htmlcs dual runner** | `pa11y-ci` | Structural issues (landmark order, heading hierarchy) + contrast that axe alone may miss | ~3 min | `apps/web/.pa11yci.json` |

Plus a dev-runtime signal (not a gate): `@axe-core/react` logs violations to the dev console while running `pnpm dev` (tree-shaken out of production; see `apps/web/src/lib/axe.ts`).

---

## Why four layers instead of one "biggest" layer

Each layer sees a **different surface** at a **different cost point**:

1. `jsx-a11y` reads source AST. Cheapest and fastest. Catches intent before render.
2. Storybook test-runner audits each story's rendered DOM in isolation — a button variant looks accessible in context but fails on hover state.
3. Playwright E2E audits the full `next start` production build. Catches composition-level issues (e.g., "this link is obscured by a fixed header").
4. `pa11y-ci` runs both the `axe` engine *and* the `htmlcs` engine. `htmlcs` (HTML CodeSniffer) catches issues `axe` doesn't — most notably heading-order mistakes, landmark uniqueness, and some contrast false-negatives.

Overlap is a feature, not a bug. If one runner regresses silently, the others catch it.

---

## WCAG tag set (the floor we gate on)

All axe-powered gates import the same tag list from `apps/web/src/lib/a11y-config.ts`:

```ts
export const AXE_WCAG_TAGS = [
  "wcag2a",     // WCAG 2.0 Level A
  "wcag2aa",    // WCAG 2.0 Level AA
  "wcag21aa",   // WCAG 2.1 Level AA (adds 1.4.11 non-text contrast, 2.5.5 target size)
  "wcag22aa",   // WCAG 2.2 Level AA (adds 2.4.11 focus not obscured, 2.5.8 target size min)
] as const;
```

**What this means in practice:** we gate at **WCAG 2.2 AA**, which is a superset of WCAG 2.1 AA. Section 508 Refresh (2017) references WCAG 2.0 AA; our floor is two generations stricter. This is the same surface the `@deployai/design-tokens` contrast suite asserts against.

`pa11y-ci` cannot import TypeScript, so its tag coupling lives as a comment in `.pa11yci.json` pointing at this doc — any drift surfaces in doc review.

---

## Axe version alignment

All axe-core consumers must resolve to the same `axe-core@4.11.x`:

- `@axe-core/react` → peer `axe-core@^4.x`
- `@axe-core/playwright` → peer `axe-core@^4.x`
- `@storybook/addon-a11y` → bundles its own axe via Storybook deps
- `axe-core` standalone → direct dependency
- `pa11y-ci` → uses the `axe` runner via its puppeteer layer

**Verification:** `pnpm why axe-core` from the repo root should report a single resolved version across all dependents. If it splits, PR review is expected to either:
- Pin all sibling packages to versions that resolve the same major.minor, **or**
- Document the divergence in the PR description with a matrix showing which rules each version exercises.

Dependabot opens PRs for `@axe-core/*` packages weekly. Hold them until all sibling bumps land together.

---

## Appeal process

No `eslint-disable-next-line jsx-a11y/*`, axe `disableRules`, or pa11y `ignore` entry lands without going through this process:

1. **File an issue** titled `A11y gate appeal: <rule-id>` in the project tracker.
2. **Describe the false-positive** (or exceptional case) in the issue body. Required fields:
   - Rule ID (e.g., `jsx-a11y/no-noninteractive-element-interactions`, `axe: region`)
   - Component / file path
   - Why the rule is wrong *for this case specifically* (not the rule in general)
   - What accessibility trade-off you're making (if any)
3. **In the PR**, add an inline comment referencing the issue and providing a one-line rationale:

   ```tsx
   // jsx-a11y gate-appeal: <rule> — <one-line rationale>. See <issue-url>.
   // eslint-disable-next-line jsx-a11y/<rule>
   ```

4. **Annual review.** Tech writer sweeps all `eslint-disable`, `disableRules`, and `ignore` entries once a year and re-validates each one's rationale. Stale suppressions get removed; the rule fires again.

**No suppressions without all four steps.** Silent disables are a compliance risk.

### Current appeals (Story 1.6 landing set)

- `ExampleForm.tsx:60` — `jsx-a11y/no-noninteractive-element-interactions` on `<form onKeyDown>` for Cmd/Ctrl+Enter submit. Rationale: keyboard shortcut is *additive* to the submit button's native behavior, not a replacement, so there's no SR-discoverability loss. **Grandfathered landing-set appeal — no tracking issue**; documented here in the Dev Agent Record for Story 1.6 and acknowledged as the one exception to the "must link an issue" rule. Re-validate on next annual sweep; file a tracking issue at that time if the appeal is still needed.

All appeals added **after** Story 1.6 MUST follow the four-step process above — the grandfathered entry is not a template.

---

## Running the gates locally

Fast feedback (matches CI job 1):

```bash
pnpm --filter @deployai/web lint
```

Storybook test-runner (matches CI job 2) — needs `storybook-static` built and served on `:6006`:

```bash
pnpm --filter @deployai/web build-storybook
pnpm dlx http-server apps/web/storybook-static --port 6006 --silent &
pnpm --filter @deployai/web storybook:test
```

Playwright E2E (matches CI job 3) — config boots its own `pnpm start`; just run:

```bash
pnpm --filter @deployai/web build
pnpm --filter @deployai/web test:e2e
```

pa11y-ci (matches CI job 4) — needs `next start` on `:3000`, plus a puppeteer Chrome install:

```bash
pnpm dlx @puppeteer/browsers@2.13.0 install chrome@147.0.7727.57 --path "$HOME/.cache/puppeteer"
pnpm --filter @deployai/web build
pnpm --filter @deployai/web exec next start --port 3000 &
pnpm --filter @deployai/web test:a11y
```

The gate-proof spec (AC10) is skipped by default; run it explicitly to validate that the axe wiring catches a known violation:

```bash
GATE_PROOF=1 pnpm --filter @deployai/web exec playwright test \
  tests/e2e/gate-catches-violation.spec.ts
```

---

## What this stack does NOT cover

The story scope fence (AC19) is deliberate:

- **Screen reader automation.** No NVDA / VoiceOver / JAWS harness in CI. Manual verification still required for release candidates.
- **Color contrast of tokens.** That's owned by `packages/design-tokens/src/__tests__/tokens.test.ts` (169 contrast + invariant assertions). Axe catches *rendered* contrast regressions; the tokens suite catches *source* contrast drift.
- **Mobile viewport a11y.** Gates run Chromium desktop only at V1. Mobile/tablet coverage lands with Story 7.13.
- **Dark mode.** Theme surface is scaffolded (Story 1.5 shadcn bridge); dark-mode-specific axe runs land with the design-system work in Epic 7.
- **Internationalization.** Only English surfaces are audited.

These are known gaps, documented here so future stories don't re-discover them.

---

## Adding a new route to pa11y-ci

When a new public route lands (e.g., `/dashboard`, `/settings`), add it
to `apps/web/.pa11yci.json`'s `urls` array so the pa11y gate audits
the full public surface, not just `/`:

```json
{
  "urls": [
    { "url": "http://127.0.0.1:3000/", "screenCapture": "pa11y-screenshots/homepage.png" },
    { "url": "http://127.0.0.1:3000/dashboard", "screenCapture": "pa11y-screenshots/dashboard.png" }
  ]
}
```

Checklist before merging the route-addition PR:

1. The route is reachable at `http://127.0.0.1:3000/<path>` via `pnpm start`
   (pa11y doesn't crawl, it only audits URLs you list explicitly).
2. A unique `screenCapture` filename under `pa11y-screenshots/` —
   lets CI's `actions/upload-artifact` step separate per-URL artifacts
   on failure.
3. `pnpm --filter @deployai/web test:a11y` passes locally against a
   production build — authentication/auth-gated routes need either a
   pre-auth step (add an `actions` entry in pa11y config) or should
   be scoped out via an explicit comment.
4. If you add an `actions` entry (custom pre-scan interactions), link
   the relevant pa11y docs in an inline `_comment` above it.

Do NOT add routes that require live third-party services. Gate them
behind an `NEXT_PUBLIC_*` feature flag and add the flagged-off
pre-auth path to pa11y instead.

---

## Writing a Storybook story that passes the addon-a11y gate

Every story added under `apps/web/src/**/*.stories.{ts,tsx}` is
automatically audited by the Storybook test-runner gate (Layer 2).
Stories that pass the addon-a11y panel locally **will** pass CI —
same tag set, same axe version, same DOM.

Minimum checklist:

1. **Render real props.** Stories that render a stub without content
   (e.g. `<Button />` with no label) routinely fail `button-name` —
   include realistic children.
2. **Use semantic roles.** Prefer `<button>`, `<a href=...>`, `<nav>`,
   `<main>`, `<header>` over generic `<div role="...">`. The former
   imply keyboard and focus behavior for free; the latter pushes that
   work onto you and usually fails `interactive-supports-focus`.
3. **Label form controls.** Every `<input>`, `<select>`, `<textarea>`
   needs an associated `<label>` (or `aria-label`, or
   `aria-labelledby`). Stories for form primitives should render them
   inside a wrapping `<label>` or alongside one.
4. **Run it locally before push.** The Storybook UI panel shows the
   same violations CI surfaces — always click through the a11y panel
   for any story you add or modify:

   ```bash
   pnpm --filter @deployai/web storybook
   # then: Stories → <your story> → A11y tab
   ```

5. **If you genuinely need an exception**, the test-runner's
   opt-out requires BOTH `disable: true` AND a `reason` string
   (see `apps/web/.storybook/test-runner.ts`). Opt-outs without a
   reason fail the gate loudly. Reasons must reference a filed
   tracking issue per the appeal process above.

---

## Future-state linkage (Stories 7.14, 7.15, 13.2)

This gate stack is the foundation; later stories consume its evidence:

- **Story 7.14 — VPAT / ACR automation.** The per-PR axe results (from
  `playwright-a11y` and `pa11y` jobs) feed a VPAT generation pipeline
  that exports a Section 508 Accessibility Conformance Report on every
  release candidate. The gate's invariant "zero violations on main"
  is what makes that report credible.
- **Story 7.15 — Screen reader automation.** Adds NVDA/VoiceOver
  assertion scripts to the Playwright layer. Relies on the four-gate
  stack being already present — the new layer is additive, not a
  replacement.
- **Story 13.2 — StateRAMP / FedRAMP control mapping.** References
  this document in the compliance matrix as evidence of
  `AC-6 (least functionality)` and `SI-10 (input validation)` control
  implementations at the UI layer. Any change to the gate set requires
  updating the control mapping in lockstep.

Treat this file as a compliance artifact. When you add or remove a
layer, update the "Cross-reference" section and open a heads-up
comment on the corresponding downstream story.

---

## On-call — who to page when a gate fires

- **`jsx-a11y` lint failure** — the PR author. Source-level fix, usually < 30 minutes.
- **`storybook-a11y` / `playwright-a11y` failure** — the PR author, then the design-system owner if the violation is in a shared primitive.
- **`pa11y` failure** — PR author, then the UX designer (Sally per BMad) for structural issues, or the tokens owner for contrast regressions.
- **All four fail simultaneously** — likely a root-layout or `globals.css` regression; escalate immediately to the a11y channel.

---

## Cross-reference

- Workflow source: `.github/workflows/a11y.yml`
- Shared tag list + disabled-rules ledger: `apps/web/src/lib/a11y-config.ts`
- Story 1.6 authoring context: `_bmad-output/implementation-artifacts/1-6-accessibility-ci-gate-stack.md`
- UX accessibility directives: `_bmad-output/planning-artifacts/ux-design-specification.md` §UX-DR26–UX-DR34
- Tokens contrast suite: `packages/design-tokens/src/__tests__/tokens.test.ts`
- Repo-wide CI conventions: `.github/workflows/README.md`
