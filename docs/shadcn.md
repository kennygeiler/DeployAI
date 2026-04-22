# DeployAI — shadcn/ui initialization and theme bridge

Story 1.5 initialized shadcn/ui in `apps/web` and wired its semantic CSS
variables to `@deployai/design-tokens`. This document is the canonical
reference for how the bridge works, what's installed, and how to add a
primitive without regressing the theme discipline Story 1.4 locked in.

## Why shadcn

shadcn's **code-ownership** model is the load-bearing choice
(`ux-design-specification.md` lines 295–315). Unlike a runtime component
library (MUI, Chakra, Mantine) where you pin a version and inherit the
library's styling assumptions, shadcn emits component source files into
your repository — you own them outright, extend them in-place, and track
upstream changes through explicit `shadcn add` regenerations.

For DeployAI this matters because:

- Every primitive renders in the DeployAI palette **without per-component
  forks** — the shadcn design accepts its color surface from CSS
  variables, so a single `@layer base :root { ... }` block covers the
  whole library.
- Radix primitives underneath every shadcn component carry WAI-ARIA and
  keyboard semantics out of the box, satisfying NFR42 (semantic ARIA
  structure) and NFR43 (accessibility-by-construction) by default rather
  than by post-hoc audit.
- When upstream ships a variant change (e.g., Button focus ring
  evolution), we choose to accept or reject the diff via
  `pnpm dlx shadcn@latest add <name>` rather than a blind `pnpm update`.

## The 23-primitive core set

Installed by Story 1.5 under `apps/web/src/components/ui/`:

| # | File | Radix / upstream dep |
|---|---|---|
| 1 | `button.tsx` | `radix-ui` (Slot), `class-variance-authority` |
| 2 | `input.tsx` | — (native `<input>`) |
| 3 | `textarea.tsx` | — (native `<textarea>`) |
| 4 | `label.tsx` | `radix-ui` (Label) |
| 5 | `form.tsx` | `react-hook-form` + `radix-ui` (Label, Slot) |
| 6 | `dialog.tsx` | `radix-ui` (Dialog) |
| 7 | `dropdown-menu.tsx` | `radix-ui` (DropdownMenu) |
| 8 | `context-menu.tsx` | `radix-ui` (ContextMenu) |
| 9 | `command.tsx` | `cmdk` |
| 10 | `popover.tsx` | `radix-ui` (Popover) |
| 11 | `hover-card.tsx` | `radix-ui` (HoverCard) |
| 12 | `tooltip.tsx` | `radix-ui` (Tooltip) |
| 13 | `tabs.tsx` | `radix-ui` (Tabs) |
| 14 | `separator.tsx` | `radix-ui` (Separator) |
| 15 | `card.tsx` | — (semantic `<div>` composition) |
| 16 | `sheet.tsx` | `radix-ui` (Dialog) |
| 17 | `badge.tsx` | — (`class-variance-authority`) |
| 18 | `avatar.tsx` | `radix-ui` (Avatar) |
| 19 | `progress.tsx` | `radix-ui` (Progress) |
| 20 | `scroll-area.tsx` | `radix-ui` (ScrollArea) |
| 21 | `accordion.tsx` | `radix-ui` (Accordion) |
| 22 | `collapsible.tsx` | `radix-ui` (Collapsible) |
| 23 | `sonner.tsx` | `sonner` + `next-themes` (peer) |

That count is deliberate. The `Table` primitive ships in Story 1.16
(admin shell) as a TanStack wrapper; every other shadcn primitive waits
for an explicit story that needs it.

## `components.json` walkthrough

`apps/web/components.json`:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": true,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/app/globals.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

Field by field:

- `style: "new-york"` — the maintained style. Upstream deprecated
  `default` in late 2025; `new-york` uses slightly tighter spacing and
  more monochrome defaults, which matches the `ux-design-specification.md`
  "calm-authority, dense-information" posture (line 305).
- `rsc: true` — Next.js 16 App Router uses React Server Components by
  default. Any primitive that manages client state (Dialog, Popover,
  DropdownMenu, Sheet, Tooltip, etc.) receives a `"use client"` pragma
  automatically from the CLI.
- `tsx: true` — we're a TypeScript codebase.
- `tailwind.config: ""` — Tailwind v4 is CSS-first; there is no JS config
  to point at. The empty string is the canonical v4 value.
- `tailwind.css: "src/app/globals.css"` — the `@import "tailwindcss"` and
  theme-bridge cascade live here.
- `tailwind.baseColor: "neutral"` — controls shadcn's **fallback** ramp
  when `cssVariables: false`. Since we run with CSS variables enabled,
  this is cosmetic — every `bg-muted` / `text-muted-foreground` resolves
  via our variable surface. `neutral` is nevertheless the closest ramp to
  our paper/ink palette for least-surprise.
- `tailwind.cssVariables: true` — the entire point of the theme-bridge
  pattern. Setting this to `false` would bake shadcn's palette into each
  generated component file and obliterate our single-source-of-truth.
- `tailwind.prefix: ""` — no utility prefix. We consume Tailwind utilities
  directly.
- `aliases.components: "@/components"`, `aliases.utils: "@/lib/utils"`,
  `aliases.ui: "@/components/ui"`, `aliases.lib: "@/lib"`,
  `aliases.hooks: "@/hooks"` — match the `paths` aliases declared in
  `apps/web/tsconfig.json` (`@/* → ./src/*`).
- `iconLibrary: "lucide"` — lucide-react is the canonical icon surface.
  Swapping to `radix-ui/react-icons` or another set is possible via the
  CLI but would require regenerating every primitive that ships with
  icons; none of our 23-primitive core set depends on icons directly
  (icons are consumed in app code).

## Theme bridge — the two-layer cascade

Every primitive renders in the DeployAI palette because
`apps/web/src/app/globals.css` authors two companion blocks:

**Layer A — `@layer base :root`**

Aliases shadcn's ~20 semantic variables onto `@deployai/design-tokens`
values. Zero literal colors.

```css
@layer base {
  :root {
    /* Surface */
    --background: var(--color-paper-100);
    --foreground: var(--color-ink-950);
    --card: var(--color-paper-200);
    --card-foreground: var(--color-ink-950);
    --popover: var(--color-paper-100);
    --popover-foreground: var(--color-ink-950);

    /* Intent */
    --primary: var(--color-evidence-700);
    --primary-foreground: var(--color-paper-100);
    --secondary: var(--color-paper-200);
    --secondary-foreground: var(--color-ink-800);
    --muted: var(--color-paper-200);
    --muted-foreground: var(--color-ink-600);
    --accent: var(--color-null-100);
    --accent-foreground: var(--color-null-600);
    --destructive: var(--color-destructive-700);
    --destructive-foreground: var(--color-paper-100);

    /* UI chrome */
    --border: var(--color-paper-300);
    --input: var(--color-stone-500);
    --ring: var(--color-evidence-700);

    /* Geometry */
    --radius: var(--radius-md);
  }
}
```

**Layer B — `@theme inline`**

Re-exports the same shadcn names into Tailwind v4's theme layer so
utilities like `bg-primary`, `text-muted-foreground`, `ring-ring`, and
`rounded-md` resolve. The `inline` modifier copies the value at compile
time — no runtime indirection.

```css
@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: var(--radius);
  --radius-lg: calc(var(--radius) + 4px);
  --radius-xl: calc(var(--radius) + 8px);
}
```

### Key mapping choices

- **`--border: var(--color-paper-300)`** — shadcn's `--border` is the
  subtle-divider tone (row separators, card outlines). `paper-300` sits
  at the "quiet surface" level that reads as a divider without
  competing for attention. `paper-400` is explicitly **not** used
  because the Story 1.4 code review classified it as decorative-only
  (it fails WCAG 2.1 SC 1.4.11 non-text contrast against `paper-100`).
- **`--input: var(--color-stone-500)`** — form-field borders are
  high-emphasis UI and need ≥ 3:1 non-text contrast against
  `--background`. `stone-500` (~`#8B8B85` vs `paper-100`'s `#FAFAF9`)
  clears that comfortably.
- **`--ring: var(--color-evidence-700)`** — aligns with the focus-ring
  shadow this design system's `shadows.focus` emits
  (`0 0 0 2px paper[100], 0 0 0 4px evidence[700]`), so DOM-level
  `outline` focus rings and CSS `box-shadow` focus rings agree on
  color.
- **`--accent: var(--color-null-100)` / `--accent-foreground: var(--color-null-600)`** —
  shadcn's `accent` drives hover backgrounds in dropdown menus, command
  palettes, etc. The null-retrieval muted neutral is the aesthetic
  match — calm, grounded, non-attention-grabbing.
- **`--radius: var(--radius-md)` → 6 px** — Layer B derives
  `--radius-sm` = `calc(var(--radius) - 4px)` = 2 px and
  `--radius-lg` = `calc(var(--radius) + 4px)` = 10 px, which match
  `radii.sm` / `radii.lg` in `@deployai/design-tokens` — no drift.

## The form stack

`react-hook-form` + `zod` + `@hookform/resolvers` + shadcn `<Form>`.
`apps/web/src/components/forms/ExampleForm.tsx` is the canonical
reference (exercised by `ExampleForm.test.tsx`).

Pattern contract (from `ux-design-specification.md` §Form Patterns and
`epics.md#UX-DR40`):

- Labels render **above** inputs. Never placeholder-as-label, never
  floating-label.
- Required indicator is asterisk (`aria-hidden="true"`) + screen-reader-
  visible "required" text — color alone violates UX-DR28
  color-independence.
- Validation mode is `onBlur` for format checks and `onSubmit` for
  completeness checks. Validation never fires on every keystroke.
- `aria-invalid` and `aria-describedby` wiring is handled by shadcn's
  `<FormControl>` / `<FormMessage>` automatically.
- Cmd+Enter (or Ctrl+Enter) submits from anywhere inside the form. The
  listener lives on the `<form>` element — not `window` — so it never
  conflicts with Cmd+K (Epic 8 command palette).

### `register` vs `Controller`

- For primitives that wrap a native `<input>`/`<textarea>`/`<select>`
  and forward a ref (`<Input>`, `<Textarea>`, `<Label>`),
  `form.register("fieldName")` is sufficient.
- For composite primitives where Radix intercepts the ref
  (`<Select>`, `<Checkbox>`, date pickers, custom toggles), use
  `<FormField>` — shadcn's thin wrapper around `<Controller>`. This is
  what `ExampleForm.tsx` uses for both email and message so future
  contributors have one pattern to copy.

## Anti-patterns

Don't:

1. **Let the shadcn CLI's injected `:root` OKLCH block survive.** If any
   hex / HSL / OKLCH color literal ends up outside
   `@deployai/design-tokens`' own emitted CSS, the bridge has failed. In
   Story 1.5 we hand-authored `components.json` before running `init`,
   so the CLI wrote nothing to `globals.css` in the first place — but
   future `shadcn add` runs may drop new variables into the file. Audit
   diffs.
2. **Install primitives outside the 23-primitive core set without
   explicit scope expansion.** The public registry has 60+ components;
   speculative installs bloat the surface and fight the design-system
   inventory in `ux-design-specification.md` §Design System Components.
   Story 1.16 adds `Table` as a TanStack wrapper; every other primitive
   waits for an explicit story.
3. **Fork a shadcn component to swap colors.** The entire point of the
   variable-bridge approach is that you never edit
   `src/components/ui/*.tsx`. If a button is rendering the wrong color,
   the mapping in `globals.css` is wrong, not the component.
4. **Hand-add `cva`, `tailwind-merge`, or `clsx` to `package.json`**
   without confirming shadcn didn't already provide them. shadcn v4 as
   of 2026-04 installs `radix-ui` unified but does **not** install
   `class-variance-authority`, `clsx`, `tailwind-merge`, or
   `lucide-react` automatically — so Story 1.5 added them explicitly.
   When the CLI's dependency resolution changes in a future release,
   re-inspect before adding by hand to avoid pin drift.
5. **Auto-render `<Toaster />` in `layout.tsx` in V1.** Sonner is
   installed so future consumers can import it, but the mount point
   belongs with the first toast consumer (Epic 7). Rendering an empty
   overlay on every route for no one is dead weight.
6. **Wrap `<html>` in `<ThemeProvider>` from `next-themes`.** V1 ships
   light-only. `next-themes` is installed only as a Sonner peer; Sonner
   falls back to `theme="light"` when no provider exists.
7. **Put DeployAI-specific code in `src/components/ui/*.tsx`.** Those
   files are regenerated on every `shadcn add`. DeployAI composites live
   in `src/components/forms/`, `src/components/features/`, or
   eventually `packages/shared-ui/`.

## Known gotchas

1. **`exactOptionalPropertyTypes` is relaxed in `apps/web`.** shadcn's
   Radix prop surfaces (`<CheckboxItem checked>`, `<Toaster theme>`,
   etc.) type `prop?: T` rather than `prop?: T | undefined`, which the
   base tsconfig's strict flag rejects. `apps/web/tsconfig.json` scopes
   the opt-out so the rest of the monorepo keeps the guard. When shadcn
   upstream tightens its prop types, consider re-enabling.
2. **`shadcn add sonner` requires `next-themes` as a peer.** pnpm with
   `--frozen-lockfile` hard-fails missing peers, so `next-themes` is a
   direct dependency even though we never mount its provider.
3. **`lucide-react ≥ 0.468` under React 19.** Earlier versions spam
   `forwardRef is deprecated` warnings in dev. If warnings appear, bump
   the peer explicitly.
4. **`FormMessage` renders nothing when there is no error.** The
   `aria-describedby` chain points at an empty element initially — RTL's
   `toHaveAccessibleDescription()` treats this as an empty description.
   After validation errors appear, the element populates and the
   description reads the error.
5. **`@theme inline` copies values at compile time.** Mutating
   `:root { --primary }` at runtime (e.g., via a tenant-branding
   override) will update the runtime CSS variable but not the baked-in
   Tailwind utility lookup. Dark mode, tenant branding, and any runtime
   theme switch need to define the utility-mapped variables (the ones
   in `@theme inline`) as well.

## How to add a new primitive

1. Run the CLI from `apps/web/`:

   ```bash
   pnpm dlx shadcn@latest add <name>
   ```

   Examples: `pnpm dlx shadcn@latest add table`,
   `pnpm dlx shadcn@latest add calendar`.

2. Inspect the diff. The CLI writes new files under
   `src/components/ui/` and may append runtime deps to `package.json`.
   It should **not** mutate `globals.css` — our `components.json`
   already has `cssVariables: true` pointing at the theme bridge. If it
   does, revert or re-wire those lines through the bridge.

3. Regenerate the lockfile: `pnpm install` (without
   `--frozen-lockfile`). Commit `pnpm-lock.yaml`.

4. Update the 23-primitive inventory in this file (add a row to the
   core-set table, or add an "Extensions" table if the primitive is
   outside the core).

5. Open a PR. Include the upstream changelog entry for the primitive so
   future regenerations have context.

## Framework support

Storybook uses `@storybook/nextjs-vite` — the officially-supported
framework for running shadcn + Next.js 16 components in Storybook. The
`"use client"` pragmas shadcn primitives carry are a no-op under Vite,
so every client-state primitive (Dialog, Popover, DropdownMenu, Sheet,
Tooltip, etc.) renders in Storybook identically to how it renders in
the Next app.

If Storybook's framework ever changes (away from `@storybook/nextjs-vite`),
re-test every primitive in the 23-primitive core set — `"use client"`
handling may behave differently.

## References

- **Story spec:** `_bmad-output/implementation-artifacts/1-5-shadcn-ui-initialization-and-theme-bridging.md`
- **Epics:** `_bmad-output/planning-artifacts/epics.md` §Story-1.5
- **UX spec:** `_bmad-output/planning-artifacts/ux-design-specification.md`
  §Component Architecture (827–853), §Button Hierarchy (859–866),
  §Form Patterns (877–883).
- **Design tokens:** [design-tokens.md](./design-tokens.md)
- **Upstream:**
  - shadcn CLI v4 (Tailwind v4 support): <https://ui.shadcn.com/docs/tailwind-v4>
  - `components.json` schema: <https://ui.shadcn.com/docs/components-json>
  - react-hook-form + zod resolver: <https://github.com/react-hook-form/resolvers>
