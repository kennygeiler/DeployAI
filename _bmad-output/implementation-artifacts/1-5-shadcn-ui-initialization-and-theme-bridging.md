# Story 1.5: shadcn/ui initialization and theme bridging

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **frontend engineer**,
I want shadcn/ui initialized in `apps/web` with its theme tokens wired to `packages/design-tokens/`,
so that every shadcn primitive renders with the DeployAI palette and subsequent component stories can compose without re-theming.

**Satisfies:** `UX-DR3` (shadcn/ui initialization — Button/Input/Textarea/Label/Form/Dialog/DropdownMenu/ContextMenu/Command/Popover/HoverCard/Tooltip/Tabs/Separator/Card/Sheet/Badge/Avatar/Progress/ScrollArea/Accordion/Collapsible/Sonner), `UX-DR39` (button hierarchy — primary/secondary/ghost/destructive, 36 px min height, 44×44 hit area, icon-only `aria-label`), `UX-DR40` (form patterns — label-above-input, required-asterisk + explicit text, on-blur format + on-submit completeness, `aria-invalid` + `aria-describedby`, Cmd+Enter submits), `NFR43` (accessibility-by-construction — Radix primitives carry keyboard + ARIA out of the box), and cements the `UX-DR1`/`UX-DR2` tokens installed by Story 1.4 as the sole source of every shadcn color/type/spacing/radius decision.

---

## Acceptance Criteria

### Epic-source (from `_bmad-output/planning-artifacts/epics.md#Story-1.5`, lines 661–676)

**AC1.** `apps/web/components.json` is present and declares:

- `"$schema": "https://ui.shadcn.com/schema.json"`.
- `"style": "new-york"` (the `default` style is deprecated upstream — per the shadcn docs, only `new-york` is maintained in 2026).
- `"rsc": true` (Next.js 16 App Router uses React Server Components).
- `"tsx": true`.
- `"tailwind": { "config": "", "css": "src/app/globals.css", "baseColor": "neutral", "cssVariables": true, "prefix": "" }` (Tailwind v4 **requires** `tailwind.config` to be an empty string — the v4 engine is CSS-first and there is no JS config file to point at).
- `"aliases": { "components": "@/components", "utils": "@/lib/utils", "ui": "@/components/ui", "lib": "@/lib", "hooks": "@/hooks" }`.
- `"iconLibrary": "lucide"`.

**AC2.** The **23-primitive core shadcn set** is installed under `apps/web/src/components/ui/`:

1. `button.tsx`
2. `input.tsx`
3. `textarea.tsx`
4. `label.tsx`
5. `form.tsx` (pulls `react-hook-form` + `@radix-ui/react-label` + `@radix-ui/react-slot`)
6. `dialog.tsx`
7. `dropdown-menu.tsx`
8. `context-menu.tsx`
9. `command.tsx` (pulls `cmdk`)
10. `popover.tsx`
11. `hover-card.tsx`
12. `tooltip.tsx`
13. `tabs.tsx`
14. `separator.tsx`
15. `card.tsx`
16. `sheet.tsx`
17. `badge.tsx`
18. `avatar.tsx`
19. `progress.tsx`
20. `scroll-area.tsx`
21. `accordion.tsx`
22. `collapsible.tsx`
23. `sonner.tsx` (the `<Toaster />` wrapper — the legacy `toast` component is deprecated upstream).

No other primitives are installed. The count is **exactly** 23.

**AC3.** `apps/web/src/app/globals.css` gains a new `@layer base { :root { ... } }` block that defines the full shadcn semantic-variable surface, with **every** value sourced from `@deployai/design-tokens` via `var(...)` — no hardcoded hex, no hardcoded HSL, no hardcoded literal colors. The block defines at minimum:

```
--background, --foreground,
--card, --card-foreground,
--popover, --popover-foreground,
--primary, --primary-foreground,
--secondary, --secondary-foreground,
--muted, --muted-foreground,
--accent, --accent-foreground,
--destructive, --destructive-foreground,
--border, --input, --ring,
--radius
```

Concrete mapping required (Dev Notes §Theme Bridge captures the full snippet):

- `--background: var(--color-paper-100)`
- `--foreground: var(--color-ink-950)`
- `--card: var(--color-paper-200)`
- `--card-foreground: var(--color-ink-950)`
- `--popover: var(--color-paper-100)`
- `--popover-foreground: var(--color-ink-950)`
- `--primary: var(--color-evidence-700)`
- `--primary-foreground: var(--color-paper-100)`
- `--secondary: var(--color-paper-200)`
- `--secondary-foreground: var(--color-ink-800)`
- `--muted: var(--color-paper-200)`
- `--muted-foreground: var(--color-ink-600)`
- `--accent: var(--color-null-100)`
- `--accent-foreground: var(--color-null-600)`
- `--destructive: var(--color-destructive-700)`
- `--destructive-foreground: var(--color-paper-100)`
- `--border: var(--color-paper-300)` (shadcn's "subtle divider" maps to a surface-tone paper, **not** the stone-500 mid-neutral — stone-500 is reserved for high-emphasis UI borders).
- `--input: var(--color-stone-500)` (form field border — needs ≥ 3:1 non-text contrast against `--background`; stone-500 clears that).
- `--ring: var(--color-evidence-700)` (focus ring color — mirrors `--shadow-focus` behavior in shadows.ts).
- `--radius: var(--radius-md)` (`6 px` — shadcn's component library derives `--radius-sm`/`--radius-lg` from `--radius` at ±2 px).

**AC4.** A Storybook story at `apps/web/src/stories/Foundations/ButtonVariants.stories.tsx` renders the shadcn `<Button>` in **every** variant × size combination required by `UX-DR39`:

- **Variants (6):** `default` (primary), `secondary`, `ghost` (tertiary), `destructive`, `link`, `outline`.
- **Sizes (4):** `default`, `sm`, `lg`, `icon`.
- **States:** enabled **and** disabled for each variant; one icon-only story that exercises `aria-label` wiring.
- Each story renders under `@storybook/addon-a11y` with zero axe-core violations (runOnly already set to `wcag2a + wcag2aa + wcag21aa + wcag22aa` in `preview.ts` — Story 1.4).
- The stories include a `meta.title = "Foundations/ButtonVariants"` so the story sits next to `Foundations/Tokens`.

**AC5.** `react-hook-form`, `zod`, and `@hookform/resolvers` are installed as **runtime dependencies** of `@deployai/web` with the following pins (confirmed via `npm view` on 2026-04-22):

- `react-hook-form@^7.73.1`
- `zod@^4.3.6`
- `@hookform/resolvers@^5.2.2`

Zod 4 is supported natively by resolvers v5.1+; no `standardSchemaResolver` fallback is needed. The type path `@hookform/resolvers/zod` exports `zodResolver` as a generic function that infers input/output types from the schema.

**AC6.** A reference component at `apps/web/src/components/forms/ExampleForm.tsx` demonstrates the canonical shadcn-Form + zod pattern:

- Declares a `const exampleFormSchema = z.object({ email: z.string().email(...), message: z.string().min(1, ...).max(500, ...) })` — two fields exercise both on-blur format validation (email) and on-submit completeness (message).
- Uses `useForm({ resolver: zodResolver(exampleFormSchema), mode: "onBlur" })`.
- Renders with shadcn's `<Form>`, `<FormField>`, `<FormItem>`, `<FormLabel>`, `<FormControl>`, `<FormMessage>`, `<FormDescription>` — **not** raw `<input>` elements.
- Labels render **above** inputs (never placeholder-as-label, never floating-label) — per UX-DR40 and `ux-design-specification.md` §Form Patterns (lines 879–883).
- Required-field indicator uses an asterisk **plus** the explicit text "required" (color-only is forbidden per UX-DR28 color-independence).
- A Cmd+Enter submit listener is wired at the `<form>` level (not globally) and triggers the same `handleSubmit` path as the `<Button type="submit">`.
- Passes `tsc --noEmit` (generics infer from the schema).
- Is covered by `apps/web/src/components/forms/ExampleForm.test.tsx` under Vitest + `@testing-library/react` (AC7).

**AC7.** `ExampleForm.test.tsx` covers — at minimum — the following scenarios and all pass:

1. **Happy-path submit:** fills email + message with valid values, clicks Submit, asserts the submission callback fires once with `{ email, message }`.
2. **Required-field error on submit:** submits with empty message, asserts `<FormMessage>` renders "Message is required" and the `<Textarea>` has `aria-invalid="true"`.
3. **On-blur format error:** types `not-an-email` into email, blurs, asserts `<FormMessage>` renders "Enter a valid email" — **and** submit has not been called (validation is on-blur, not on-change, so the form doesn't flash errors on every keystroke).
4. **Cmd+Enter submit:** presses `Meta+Enter` while focus is inside the form, asserts the submission callback fires.
5. **ARIA wiring:** asserts `aria-invalid` flips to `"true"` when a field has errors and back to `"false"` when resolved; asserts each `<FormMessage>` is linked to its input via `aria-describedby` (React Testing Library's `toHaveAccessibleDescription` helper makes this a one-liner).
6. **Label-above-input:** asserts every input has a visible `<label>` above it (no placeholder-as-label, no `aria-label` shortcuts).

No snapshot tests. Semantic RTL queries only.

---

### Cross-cutting (wiring, Turbo, CI, governance)

**AC8.** `apps/web/src/lib/utils.ts` exports the `cn` helper (the canonical shadcn `clsx` + `tailwind-merge` composition):

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

`clsx`, `tailwind-merge`, and `class-variance-authority` are installed **transitively** through the shadcn CLI as runtime deps of the generated component files. Do **not** add them by hand in `package.json` before running the CLI — they arrive via `shadcn add`.

**AC9.** `apps/web/src/components/ui/` is present (one of shadcn's `aliases.ui` destinations). The files generated by `shadcn add` are **not** reformatted — the upstream repository is the source of truth for whitespace, import order, and TypeScript style inside these files. We treat the directory as vendored third-party code for linting/formatting purposes (AC10).

**AC10.** `apps/web/eslint.config.mjs` adds `src/components/ui/**` to its `globalIgnores` (or equivalent flat-config `ignores` entry) alongside the existing Storybook build-output ignore. This matches how the upstream shadcn repo ships code with its own lint conventions — we avoid re-formatting it so future `shadcn add` diffs stay clean. `.prettierignore` receives a matching entry.

**AC11.** `apps/web/package.json` declares the new dependencies with the pins from AC5 plus the shadcn-transitive runtime deps:

```json
"dependencies": {
  "@deployai/design-tokens": "workspace:*",
  "@hookform/resolvers": "^5.2.2",
  "@radix-ui/react-accordion": "^1.x",          // inserted by `shadcn add accordion`
  "@radix-ui/react-avatar": "^1.x",
  "@radix-ui/react-collapsible": "^1.x",
  "@radix-ui/react-context-menu": "^2.x",
  "@radix-ui/react-dialog": "^1.x",
  "@radix-ui/react-dropdown-menu": "^2.x",
  "@radix-ui/react-hover-card": "^1.x",
  "@radix-ui/react-label": "^2.x",
  "@radix-ui/react-popover": "^1.x",
  "@radix-ui/react-progress": "^1.x",
  "@radix-ui/react-scroll-area": "^1.x",
  "@radix-ui/react-separator": "^1.x",
  "@radix-ui/react-slot": "^1.x",
  "@radix-ui/react-tabs": "^1.x",
  "@radix-ui/react-tooltip": "^1.x",
  "class-variance-authority": "^0.7.1",
  "clsx": "^2.1.1",
  "cmdk": "^1.1.1",
  "lucide-react": "^0.468.0",                   // pin ≥ 0.468 — drops forwardRef warnings under React 19
  "next": "16.2.4",
  "next-themes": "^0.4.6",                      // Sonner peer; required even though V1 is light-only
  "react": "19.2.4",
  "react-dom": "19.2.4",
  "react-hook-form": "^7.73.1",
  "sonner": "^2.0.7",
  "tailwind-merge": "^3.5.0",
  "tw-animate-css": "^1.4.0",                   // Tailwind v4 replacement for deprecated `tailwindcss-animate`
  "zod": "^4.3.6"
}
```

(Radix peer versions are whatever `shadcn@latest add` resolves on the date of implementation — the dev agent should let the CLI pick them and commit the result.)

**AC12.** `apps/web/package.json` **does not** add any of the shadcn-transitive deps (`cva`, `tailwind-merge`, `clsx`) to `devDependencies`. They must live in `dependencies` because they're imported by runtime component code.

**AC13.** `apps/web/package.json` optionally adds a convenience script `"ui:add": "pnpm dlx shadcn@latest add"` so future primitive additions go through the canonical CLI path. (Not required, but recommended.)

**AC14.** `pnpm install --frozen-lockfile` at the repo root reproduces cleanly after the lockfile is regenerated. `pnpm-lock.yaml` is committed.

**AC15.** `pnpm turbo run lint typecheck test build` remains green. The task count stays at **20/20** successful because Story 1.5 adds no new workspace — it extends `apps/web` only. (If the dev agent opts to pre-emptively land `packages/shared-ui/` as an empty stub, the count becomes 24/24, but per the scope fence in AC24 below, `packages/shared-ui/` is Story 7.x territory — do **not** create it.)

**AC16.** `pnpm --filter @deployai/web build-storybook` still exits 0 and the new `Foundations/ButtonVariants` stories appear in `storybook-static/`.

**AC17.** Story 1.4's `Foundations/Tokens.stories.tsx` still renders without regressions — same four stories, same axe-core clean output, no broken imports.

**AC18.** `apps/web/src/app/page.test.tsx` (baseline from Story 1.3) still passes.

**AC19.** Story 1.2's 5-job CI gate (`toolchain-check`, `smoke`, `sbom-source`, `cve-scan`, `dependency-review`) remains green. No GitHub Actions workflow changes are made in Story 1.5.

**AC20.** `pnpm format:check` remains clean. `src/components/ui/**` is in `.prettierignore` so shadcn-authored files don't trigger format drift.

**AC21.** A new doc `docs/shadcn.md` is authored and covers:

- What shadcn is and why we chose it (code-ownership model — components are vendored, not runtime deps per `ux-design-specification.md` lines 297–300).
- The `components.json` config, field by field, with rationale (why `new-york`, why `neutral` base color, why `cssVariables: true`, why `rsc: true`).
- The theme-bridge pattern — the `@layer base :root {}` block that aliases shadcn semantic variables onto `@deployai/design-tokens` — with the full CSS snippet.
- Anti-patterns (never edit generated `ui/*.tsx` files for cosmetics; never install primitives outside the 23-primitive core set without adding to the scope fence; never hardcode HSL; never add `cva` as a direct dep).
- How to add a new primitive: `pnpm dlx shadcn@latest add <name>` → it lands under `src/components/ui/` → update this doc's primitive inventory → open a PR.
- The form stack — `react-hook-form` + `zod` + `@hookform/resolvers` + shadcn `<Form>` — with a summary of how `Controller` bridges refs to composite primitives (Select, DatePicker, Checkbox) vs the simpler `register` path for primitives like `<Input>`.
- The Cmd+Enter convention (form-scoped, not global; lives in a small `useCmdEnterSubmit` hook or inline `onKeyDown`).

**AC22.** `docs/repo-layout.md` gains a "What Story 1.5 shipped" section mirroring the Story 1.4 row format, and the "What this repo does NOT yet contain (by design)" list has the `No shadcn/ui init — Story 1.5.` bullet struck/removed.

**AC23.** `docs/design-tokens.md`'s "shadcn/ui bridge — Story 1.5" section is updated in place: the pseudo-snippet becomes the **actual** shipped CSS, with a link to `docs/shadcn.md` for the full story. No duplication between the two files — `docs/design-tokens.md` owns the token-side explanation, `docs/shadcn.md` owns the component-side.

**AC24.** Scope fence — what this story does **NOT** do:

- No `packages/shared-ui/` workspace. Shared primitives land in Epic 7.
- No DeployAI-specific composite components (`CitationChip`, `EvidencePanel`, `PhaseIndicator`, `FreshnessChip`, `OverrideComposer`, etc.). Those are Epic 7 (UX-DR4–12).
- No dark-mode theme block. `next-themes` is installed because Sonner declares it as a peer, but no `<ThemeProvider>` wrapping happens in this story — the root layout stays light-only. V1 ships light-theme per `ux-design-specification.md` line 468.
- No `Table` primitive. The shadcn `Table` in Story 1.16 (admin shell) is a TanStack wrapper and lives outside the 23-primitive core set.
- No `<Toaster />` rendered in `layout.tsx`. Render sites for Sonner come in Epic 7 when the first toast consumer lands; in Story 1.5 we only install the `sonner.tsx` wrapper so it's available.
- No accessibility CI gate workflow (axe-playwright, pa11y, `.github/workflows/a11y.yml`, `eslint-plugin-jsx-a11y` at `error`) — Story 1.6.
- No CVA / button-variant customizations beyond shadcn defaults. The variants ship as authored upstream; we only map the color layer via `@layer base :root`.
- No Storybook stories for other primitives (Input, Textarea, Form, Dialog, etc.). Only `ButtonVariants` is required by AC4; the rest arrive in Epic 7 as the components are consumed.
- No Chromatic / visual regression. Epic 7.

---

## Tasks / Subtasks

### Phase 0 — Prep

- [ ] Pull `main`, verify `pnpm install --frozen-lockfile` + `pnpm turbo run lint typecheck test build` still green after Story 1.4 (baseline). (AC14, AC15)
- [ ] Re-read `ux-design-specification.md` §Component Architecture + §Button Hierarchy + §Form Patterns (lines 827–853, 859–866, 877–883) for the exact primitive set and pattern contracts.
- [ ] Re-read `epics.md#Story-1.5` (lines 661–676) for the epic-source ACs and the 23-primitive enumeration.
- [ ] Re-read `docs/design-tokens.md#shadcn/ui bridge — Story 1.5` for the token-mapping plan and confirm every variable maps to a real token from `@deployai/design-tokens/tokens.css`.
- [ ] Confirm `apps/web/.storybook/preview.ts` already imports `globals.css`, so the new shadcn semantic variables will propagate into every story automatically.

### Phase 1 — shadcn CLI init

- [ ] From `apps/web/`, run `pnpm dlx shadcn@latest init` (the stable CLI v4, released March 2026, supports Tailwind v4 + React 19 — no `@canary` required).
- [ ] During the interactive prompt, select:
  - style: **new-york**
  - base color: **neutral**
  - CSS variables: **yes**
  - global CSS file: `src/app/globals.css`
  - React Server Components: **yes**
  - tsx: **yes**
  - components alias: `@/components`
  - utils alias: `@/lib/utils`
  - ui alias: `@/components/ui`
  - icon library: **lucide**
- [ ] Verify `apps/web/components.json` exists and matches the AC1 schema. (AC1)
- [ ] Verify `apps/web/src/lib/utils.ts` exists with the canonical `cn` helper. (AC8)
- [ ] Inspect the `@layer base :root {}` block the CLI injected into `apps/web/src/app/globals.css`. **Do not yet modify it** — Phase 3 rewires every value to tokens in one pass.
- [ ] Inspect `apps/web/src/app/globals.css` for any injected `@plugin "tw-animate-css"` line (shadcn's default since Tailwind v3 `tailwindcss-animate` was deprecated); leave as-is.

### Phase 2 — Install the 23-primitive core set

- [ ] From `apps/web/`, run **one** batched CLI invocation:
  ```bash
  pnpm dlx shadcn@latest add \
    button input textarea label form \
    dialog dropdown-menu context-menu command \
    popover hover-card tooltip tabs separator \
    card sheet badge avatar progress scroll-area \
    accordion collapsible sonner
  ```
- [ ] Confirm exactly 23 files in `apps/web/src/components/ui/` (plus the `utils.ts` created in Phase 1 — **not** in `components/ui/`, but in `lib/`). Enumerate and check:
  - [ ] `button.tsx`
  - [ ] `input.tsx`
  - [ ] `textarea.tsx`
  - [ ] `label.tsx`
  - [ ] `form.tsx`
  - [ ] `dialog.tsx`
  - [ ] `dropdown-menu.tsx`
  - [ ] `context-menu.tsx`
  - [ ] `command.tsx`
  - [ ] `popover.tsx`
  - [ ] `hover-card.tsx`
  - [ ] `tooltip.tsx`
  - [ ] `tabs.tsx`
  - [ ] `separator.tsx`
  - [ ] `card.tsx`
  - [ ] `sheet.tsx`
  - [ ] `badge.tsx`
  - [ ] `avatar.tsx`
  - [ ] `progress.tsx`
  - [ ] `scroll-area.tsx`
  - [ ] `accordion.tsx`
  - [ ] `collapsible.tsx`
  - [ ] `sonner.tsx`
- [ ] Verify `apps/web/package.json` gained `@radix-ui/*` runtime deps + `cmdk`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `sonner`, `next-themes`, `tw-animate-css` via the CLI. (AC11, AC12)
- [ ] Run `pnpm install --frozen-lockfile` at the repo root — expect it to fail since the CLI mutated `package.json`; re-run `pnpm install` (no flag) to regenerate `pnpm-lock.yaml`, then assert a clean `--frozen-lockfile` re-run. (AC14)

### Phase 3 — Theme bridge (the core of this story)

- [ ] Rewrite the shadcn-injected `@layer base :root {}` block in `apps/web/src/app/globals.css` so **every** variable references a token. Use this exact mapping:

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

  (AC3)

- [ ] **Delete** any `.dark { ... }` block the shadcn CLI injected. V1 ships light-only per `ux-design-specification.md` line 468. A comment documents why:
  ```css
  /* Dark mode is deferred — V1 ships light-only per ux-design-specification.md §Visual Foundation (line 468). */
  ```
- [ ] **Delete** any hardcoded `oklch(...)` / `hsl(...)` / hex color the shadcn CLI injected into `:root` outside the `@layer base` block. Every color must flow from `@deployai/design-tokens`. (AC3)
- [ ] Leave the `@plugin "tw-animate-css"` line in place — Tailwind v4 needs it for the `tw-animate-*` utility classes that shadcn primitives use (e.g., `animate-in`, `fade-out-0`). If the CLI added `@import "tw-animate-css"` instead, keep that variant.
- [ ] Verify by temporarily rendering `<Button>` in `page.tsx` dev server that the button fill is `--color-evidence-700` (visually teal-blue) — then revert the `page.tsx` edit.

### Phase 4 — ESLint + Prettier ignore shadcn code

- [ ] `apps/web/eslint.config.mjs` — extend `globalIgnores` with `src/components/ui/**`. (AC10)
- [ ] `apps/web/.prettierignore` — add `src/components/ui/` if the repo's Prettier setup doesn't already inherit the ESLint-ignore equivalent. (The root `.prettierignore` is the likely location; append there if `apps/web/` has no local file.)
- [ ] Run `pnpm --filter @deployai/web lint` and `pnpm format:check` — both must be clean after the ignores land. If lint catches anything in the shadcn files, the ignore pattern is wrong. (AC20)

### Phase 5 — `ExampleForm.tsx` reference component

- [ ] Create `apps/web/src/components/forms/ExampleForm.tsx`. Shape:

  ```tsx
  "use client";

  import { zodResolver } from "@hookform/resolvers/zod";
  import { useForm } from "react-hook-form";
  import { z } from "zod";

  import { Button } from "@/components/ui/button";
  import {
    Form, FormControl, FormDescription, FormField,
    FormItem, FormLabel, FormMessage,
  } from "@/components/ui/form";
  import { Input } from "@/components/ui/input";
  import { Textarea } from "@/components/ui/textarea";

  const exampleFormSchema = z.object({
    email: z.string().email("Enter a valid email"),
    message: z
      .string()
      .min(1, "Message is required")
      .max(500, "Message must be 500 characters or fewer"),
  });

  export type ExampleFormValues = z.infer<typeof exampleFormSchema>;

  export function ExampleForm({
    onSubmit,
  }: {
    onSubmit: (values: ExampleFormValues) => void;
  }) {
    const form = useForm<ExampleFormValues>({
      resolver: zodResolver(exampleFormSchema),
      mode: "onBlur",
      defaultValues: { email: "", message: "" },
    });

    return (
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              void form.handleSubmit(onSubmit)();
            }
          }}
          className="space-y-4"
          noValidate
        >
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Email <span aria-hidden="true">*</span>{" "}
                  <span className="sr-only">required</span>
                </FormLabel>
                <FormControl>
                  <Input type="email" autoComplete="email" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="message"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Message <span aria-hidden="true">*</span>{" "}
                  <span className="sr-only">required</span>
                </FormLabel>
                <FormControl>
                  <Textarea rows={5} {...field} />
                </FormControl>
                <FormDescription>Cmd+Enter submits the form.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button type="submit">Submit</Button>
        </form>
      </Form>
    );
  }
  ```

  (AC6)

- [ ] Verify `pnpm --filter @deployai/web typecheck` is clean — zodResolver should infer `ExampleFormValues` automatically.

### Phase 6 — `ExampleForm.test.tsx`

- [ ] Create `apps/web/src/components/forms/ExampleForm.test.tsx` covering the six scenarios in AC7. Use `@testing-library/react` + `@testing-library/jest-dom` + `@testing-library/user-event` (already devDeps).
- [ ] Ensure the test setup calls `userEvent.setup()` — `fireEvent` won't trigger the blur semantics react-hook-form needs for `mode: "onBlur"`.
- [ ] For the Cmd+Enter case, use `user.keyboard("{Meta>}{Enter}{/Meta}")` (userEvent v14 syntax). Verify the submit callback receives `{ email, message }`.
- [ ] For the ARIA wiring case, assert both `aria-invalid="true"` and `toHaveAccessibleDescription("Message is required")` when the message field errors.
- [ ] Run `pnpm --filter @deployai/web test` — expect the new test file to discover and pass.

### Phase 7 — `ButtonVariants.stories.tsx`

- [ ] Create `apps/web/src/stories/Foundations/ButtonVariants.stories.tsx`:

  ```tsx
  import type { Meta, StoryObj } from "@storybook/nextjs-vite";
  import { Mail } from "lucide-react";

  import { Button } from "@/components/ui/button";

  const meta = {
    title: "Foundations/ButtonVariants",
    component: Button,
    parameters: { layout: "centered" },
    tags: ["autodocs"],
  } satisfies Meta<typeof Button>;

  export default meta;
  type Story = StoryObj<typeof meta>;

  export const AllVariants: Story = {
    render: () => (
      <section aria-labelledby="button-variants-heading" className="space-y-4">
        <h2 id="button-variants-heading" className="sr-only">All Button variants</h2>
        <div className="flex gap-2"><Button>Default</Button><Button variant="secondary">Secondary</Button><Button variant="ghost">Ghost</Button><Button variant="destructive">Destructive</Button><Button variant="link">Link</Button><Button variant="outline">Outline</Button></div>
      </section>
    ),
  };

  export const AllSizes: Story = {
    render: () => (
      <section aria-labelledby="button-sizes-heading" className="space-y-4">
        <h2 id="button-sizes-heading" className="sr-only">All Button sizes</h2>
        <div className="flex items-center gap-2"><Button size="sm">Small</Button><Button size="default">Default</Button><Button size="lg">Large</Button><Button size="icon" aria-label="Send mail"><Mail aria-hidden /></Button></div>
      </section>
    ),
  };

  export const DisabledStates: Story = {
    render: () => (
      <section aria-labelledby="button-disabled-heading" className="space-y-4">
        <h2 id="button-disabled-heading" className="sr-only">Disabled Button states</h2>
        <div className="flex gap-2"><Button disabled>Default</Button><Button variant="secondary" disabled>Secondary</Button><Button variant="ghost" disabled>Ghost</Button><Button variant="destructive" disabled>Destructive</Button></div>
      </section>
    ),
  };

  export const IconOnlyHasAriaLabel: Story = {
    render: () => (
      <Button size="icon" aria-label="Open menu"><Mail aria-hidden /></Button>
    ),
  };
  ```

  (AC4)

- [ ] Run `pnpm --filter @deployai/web build-storybook` — verify the new stories appear under `Foundations/ButtonVariants`, and the a11y addon reports zero violations. (AC16)

### Phase 8 — Documentation

- [ ] Author `docs/shadcn.md` per AC21. Sections:
  - Why shadcn (code-ownership, Radix accessibility, architectural decision in `ux-design-specification.md` lines 295–315).
  - `components.json` walkthrough (every field, with rationale).
  - The theme bridge — the full `@layer base :root` block plus why each shadcn var maps to the chosen token. Explicitly note: shadcn's default HSL palette is replaced; every surface flows from `@deployai/design-tokens`.
  - The 23-primitive core set — enumerate and link each primitive to its upstream docs.
  - The form stack: react-hook-form + zod + `zodResolver`. Explain `Controller` vs `register` for composite primitives.
  - Cmd+Enter convention (form-scoped).
  - Anti-patterns (5 items; mirror Dev Notes §Anti-patterns here).
  - "How to add a new primitive" — `pnpm dlx shadcn@latest add <name>`, update `docs/shadcn.md` inventory, PR.
- [ ] Update `docs/repo-layout.md`:
  - Append a "What Story 1.5 shipped" section (mirror the Story 1.4 row format — describe what `apps/web` gained).
  - Strike/remove the `No shadcn/ui init — Story 1.5.` bullet from the "What this repo does NOT yet contain" list.
  - (AC22)
- [ ] Update `docs/design-tokens.md#shadcn/ui bridge — Story 1.5`:
  - Replace the pseudo-snippet with the actual CSS block that shipped.
  - Add a one-line link: `See [docs/shadcn.md](./shadcn.md) for the full shadcn initialization story.`
  - (AC23)

### Phase 9 — Verify + PR

- [ ] Full verification:
  - [ ] `pnpm install --frozen-lockfile` → clean.
  - [ ] `pnpm turbo run lint typecheck test build` → 20/20 successful.
  - [ ] `pnpm --filter @deployai/web build-storybook` → exits 0; `Foundations/ButtonVariants` + `Foundations/Tokens` both present.
  - [ ] `pnpm format:check` → clean (no drift in `src/components/ui/**` because the directory is ignored).
  - [ ] `pnpm --filter @deployai/web test` → passes, including the new `ExampleForm.test.tsx`.
- [ ] Commit on `cursor/story-1-5-ready-for-dev` (already the active branch), push, open PR #5.
- [ ] Poll CI; iterate until all 5 jobs green (dependency-review still gated on GHAS).
- [ ] Flip story + sprint-status to `review`; fill Dev Agent Record (debug log, completion notes, file list, change log).

---

## Dev Notes

### Why this story matters

Story 1.4 gave the repo a typed, CSS-variable-backed source of truth for every color, spacing value, typography setting, shadow, radius, elevation, and motion duration. Story 1.5 is the story that turns those tokens into a component library. Every primitive that renders after this — the Button in the Morning Digest, the Dialog on break-glass confirmation, the Command palette bound to Cmd+K, the Form that edits an Override — inherits the DeployAI palette because of the `@layer base :root {}` block this story lands.

Getting the bridge right **once** means:

1. When the palette shifts (e.g., "evidence-700 needs to shift 4% warmer"), exactly one file changes (`packages/design-tokens/src/colors.ts`), the tokens package rebuilds, and every shadcn-rendered surface updates.
2. When a future story adds a new DeployAI primitive (CitationChip, EvidencePanel), the primitive composes on top of shadcn's variable surface — no double-theming.
3. When a dark-mode token set lands later, flipping requires adding one `.dark { ... }` block; no component code changes.

Getting the bridge **wrong** (hardcoding HSL, forking button variants, letting shadcn's default slate bleed through) is the worst kind of debt — it's distributed across 23 files and only reveals itself during the first customer demo.

### shadcn CLI v4 — Tailwind v4 status (2026-04-22)

As of the March 2026 `shadcn/cli v4` release, the **stable** CLI (`shadcn@latest`) supports Tailwind v4 + React 19 + Next.js 16 natively. The earlier guidance to use `shadcn@canary` is obsolete. Verification path (April 2026):

- `pnpm dlx shadcn@latest --version` → should print a `4.x` major.
- `npx shadcn@latest init` → prompts include `style: new-york` (default deprecated), `baseColor: neutral`, `cssVariables: true`.
- `components.json` written by the CLI has `tailwind.config: ""` (blank — Tailwind v4 is CSS-first; no JS config to point at).
- The injected `@layer base :root {}` block uses OKLCH values by default (new neutral palette). We replace the whole block with `var(...)` references to tokens — no OKLCH values survive.

If the dev agent discovers on the day of implementation that the stable CLI still can't handle Tailwind v4 cleanly, **fall back to `shadcn@canary`** and note the exact version in Dev Agent Record's "Agent Model Used" section. Do not silently switch channels.

### Why `style: "new-york"` and not `default`

shadcn deprecated the `default` style in late 2025; `new-york` is the maintained style and the one every component in the public registry ships for. It's also the style the DeployAI architecture decisions (`ux-design-specification.md` line 305) implicitly selected by choosing "calm-authority, dense-information" aesthetics — `new-york` uses tighter spacing and slightly more monochrome defaults than the retired `default` style.

### Why `baseColor: "neutral"` and not `stone` / `zinc`

shadcn's `baseColor` controls the **fallback** neutral ramp the generated components reach for **only** when `cssVariables` is false. With `cssVariables: true`, every `bg-muted` / `text-muted-foreground` class resolves via `--muted` / `--muted-foreground`, which we override in `@layer base`. So `baseColor` is effectively cosmetic in our setup — but `neutral` is the closest match to our paper/ink palette, so we pick it for least-surprise if a future story ever flips `cssVariables` off.

### Theme bridge — design rationale

The bridge lives in `apps/web/src/app/globals.css` as a **second** `@layer base { :root { ... } }` block (the first is whatever Tailwind v4's `@theme` / `@deployai/design-tokens/tailwind` emits). Two layers, one cascade:

1. **Layer A — Tailwind v4 `@theme` (from `@deployai/design-tokens/tailwind`)**
   Emits `--color-ink-950`, `--spacing-4`, `--text-body`, `--font-sans`, `--radius-md`, `--shadow-sm`, etc. These are the *literal* token names — one per source-of-truth value.

2. **Layer B — shadcn semantic aliases (authored in Story 1.5)**
   Maps shadcn's ~20 semantic names (`--primary`, `--muted-foreground`, `--ring`, etc.) onto the Layer A tokens via `var(...)`. Zero literal values. Every shadcn primitive reads from Layer B; Layer B reads from Layer A; Layer A reads from `@deployai/design-tokens`.

Rules:

- **Never** hardcode a value in Layer B. Every variable is `var(--color-…)`, `var(--radius-…)`, or similar.
- **Never** duplicate a token name across both layers. (E.g., don't define `--primary: #1F4A8C` in Layer B — always `var(--color-evidence-700)`.)
- **Never** fork a shadcn component file to swap colors. If the color is wrong, the bridge mapping is wrong.

### Concrete bridging snippet (the one that ships)

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

Key choices, annotated:

- **`--border: var(--color-paper-300)`.** shadcn uses `--border` for subtle dividers — row separators in dropdowns, card outlines. These want the paper-300 surface tone (≈`#E5E5E2`), not the mid-neutral `stone-500`. We explicitly do **not** map `--border` to `paper-400` because `paper-400` is now decorative-only per the Story 1.4 review (it fails 3:1 non-text contrast against `paper-100`). Review finding #3 (`packages/design-tokens/src/colors.ts` line 35–40 comment) enforces this.
- **`--input: var(--color-stone-500)`.** Form field borders are high-emphasis UI — they need ≥ 3:1 non-text contrast against `--background`. `stone-500` (≈`#8B8B85` vs `#FAFAF9`) clears this comfortably. `paper-300` / `paper-400` would not.
- **`--ring: var(--color-evidence-700)`.** Matches `shadows.focus` (focus ring shadow) from Story 1.4, so the DOM-level `outline: 2px solid var(--ring)` AND the `box-shadow`-based focus ring from tokens agree on color.
- **`--accent: var(--color-null-100)` / `--accent-foreground: var(--color-null-600)`.** shadcn's `accent` is used for hover backgrounds in dropdown menus, command-palette results, etc. The null-retrieval muted neutral is the aesthetic match — calm, grounded, not attention-grabbing.
- **`--destructive-foreground: var(--color-paper-100)`.** Paper-on-destructive is 7.1:1 (AAA). We never use destructive-100 as a destructive foreground because the chip-background pair is already covered elsewhere.
- **`--radius: var(--radius-md)`.** 6 px. shadcn's components derive `--radius-sm` = `calc(var(--radius) - 4px)` and `--radius-lg` = `calc(var(--radius) + 4px)` internally. That gives us 2 px / 10 px at the component level, which matches `radii.sm` / `radii.lg` from Story 1.4 — no drift.

### Anti-patterns (don't do)

1. **Do not let the shadcn CLI's injected `:root` block survive.** The CLI writes OKLCH values into `globals.css` as `:root { --primary: oklch(0.205 0 0); ... }`. Replace **every** value with `var(...)` references to `@deployai/design-tokens` tokens. If any OKLCH / HSL / hex literal survives outside `@deployai/design-tokens`'s own emitted CSS, the bridge has failed.
2. **Do not install primitives outside the 23-primitive core set.** The shadcn public registry has 60+ components; installing them speculatively bloats the surface and fights the `ux-design-specification.md` component inventory (§Design System Components, lines 726–747). Story 1.16 adds `Table` for the admin shell; every other primitive arrives via a future story + explicit scope expansion.
3. **Do not fork the Button (or any shadcn) component to customize colors.** The entire point of the variable-bridge approach is that you never edit `src/components/ui/button.tsx`. If the button is rendering the wrong color, the mapping in `globals.css` is wrong, not the component.
4. **Do not add `cva`, `tailwind-merge`, or `clsx` to `apps/web/package.json` by hand.** They arrive as runtime deps of the generated component files via `shadcn add`. Hand-adding them creates pin drift when the CLI later bumps peers.
5. **Do not auto-render `<Toaster />` in `layout.tsx` yet.** Sonner is installed (AC2) so consumers can import it, but the actual `<Toaster />` mount point belongs with the first toast consumer — likely an Epic 7 feature component. Rendering it in `layout.tsx` for no-one creates an empty overlay node on every route.
6. **Do not install `@storybook/addon-interactions` or similar.** Storybook's interaction tests are lovely but out-of-scope; Vitest + RTL is the form-testing channel for V1.
7. **Do not wrap `<html>` in `<ThemeProvider>` from `next-themes`.** V1 is light-only. `next-themes` is installed because Sonner peer-depends on it, but no provider wraps the tree. (Sonner reads `next-themes`'s `useTheme()` hook defensively; when no provider exists, it falls back to `theme="light"` — which is what we want.)

### Known gotchas

1. **shadcn CLI v4 + Tailwind v4 `@theme` interaction.** The CLI's injected `:root` sits **outside** the `@theme {}` block the tokens package emits. That's intentional — `@theme` declares design-time tokens, `:root` declares runtime CSS variables. Both are valid; the `:root` block overrides nothing in `@theme` because they don't share variable names. If the CLI ever starts emitting `@theme` directly, re-read the theme bridge section here before diverging.
2. **Sonner 2.x + `next-themes` peer.** Sonner 2.x moved `next-themes` to a peer dep. If it's missing, `npm install sonner` fails with a peer-dep warning that pnpm will likely hard-fail on due to `--frozen-lockfile`. Install `next-themes` explicitly (AC11).
3. **`lucide-react` + React 19 forwardRef warnings.** Lucide 0.468+ dropped `forwardRef` wrapping in favor of React 19's native ref-as-prop pattern. Any version < 0.468 will spam console warnings under React 19.2. Let the shadcn CLI pick the peer — it pins a recent version automatically — but verify in browser devtools that no Lucide warnings appear.
4. **`react-hook-form` v7 + `useFormContext` generic inference.** For primitives that shadcn wraps (`<Input>`, `<Textarea>`, `<Label>`), `register` is fine. For composite primitives that don't forward a ref to a native `<input>` (`<Select>`, custom `<Checkbox>`, date pickers), you **must** use `<Controller control={form.control} name="..." render={...} />` because `register`'s ref forwarding breaks through the Radix slot. The `<FormField>` primitive shadcn ships is a thin `<Controller>` wrapper and handles this automatically — use `<FormField>` for any composite input, which `ExampleForm.tsx` does for both email and message fields.
5. **Cmd+Enter submission.** Attach at the `<form>` level, not globally via `window.addEventListener`. A global listener conflicts with Cmd+K command-palette hotkeys (Epic 8). Also preferred over a `useHotkeys`-style hook because it keeps the submission path inside the form's scope — clicking outside then Cmd+Enter does nothing, which is the correct UX.
6. **`components.json` `rsc: true` means shadcn adds `"use client"` directives automatically** to any primitive that needs client-side state (Dialog, Popover, DropdownMenu, etc.). This is correct for Next.js 16 App Router — don't disable it.
7. **Tailwind v4 `@theme inline` vs non-inline.** The design-tokens package emits `@theme { ... }` (not `@theme inline`). The non-inline form lets consumers override variables at runtime via CSS cascade; `@theme inline` bakes them in at compile time. For our use case (future dark-mode / tenant-branded themes), non-inline is the correct choice and nothing in Story 1.5 changes that.
8. **Storybook's `<ButtonVariants>` stories with `size="icon"` must include `aria-label`.** The a11y addon's `runOnly` includes `wcag2aa` (SC 1.1.1 "Non-text Content"). Icon-only buttons without `aria-label` fail `button-name`. The canonical fix is `aria-label="..."` on the button and `aria-hidden` on the inner `<Icon />`.
9. **`FormMessage` default behavior.** shadcn's `<FormMessage>` renders nothing when `!error && !message`. This means the `aria-describedby` chain initially points at an empty element — RTL's `toHaveAccessibleDescription()` correctly treats this as an empty description. After validation errors appear, the same element populates and the description reads the error string.
10. **Generated `ui/*.tsx` files change between shadcn releases.** When upstream ships a Button variant change, regenerating via `pnpm dlx shadcn@latest add button` overwrites our local copy. That's by design. Don't put DeployAI-specific code in `ui/*.tsx` — put composites in `components/forms/`, `components/features/`, or eventually `packages/shared-ui/`.
11. **ESLint flat-config `globalIgnores` vs `ignores`.** Story 1.4's `apps/web/eslint.config.mjs` uses the `globalIgnores` helper from `eslint/config`. Keep using that helper for consistency; don't mix flat-config `ignores` arrays.

### Testing strategy

- **Form behavior → Vitest + RTL.** `ExampleForm.test.tsx` covers the six scenarios in AC7. Use `@testing-library/user-event@14`, not `fireEvent`. Every query is semantic (`getByRole`, `getByLabelText`, `getByText`) — no `container.querySelector`, no DOM traversal, no snapshots.
- **Button visuals → Storybook + addon-a11y.** `ButtonVariants.stories.tsx` renders every variant × size × state combo. The a11y addon runs axe-core (wcag2a + wcag2aa + wcag21aa + wcag22aa from Story 1.4's preview.ts) and must report zero violations.
- **Component-level unit tests for shadcn primitives:** out of scope. The upstream shadcn repo tests its own primitives; our tests cover **composition** (ExampleForm = Button + Input + Textarea + Form).
- **Chromatic / visual-regression:** out of scope (Epic 7).

### `ExampleForm.tsx` design rationale

- **Two fields, two validation modes.** `email` validates on blur (format check) and `message` validates on blur (length check) + on submit (required). This is the minimum set that exercises both on-blur format and on-submit completeness per UX-DR40.
- **Required indicator uses asterisk + sr-only "required" text.** The asterisk is decorative (`aria-hidden="true"`); the screen-reader-visible text carries the semantic meaning. This is the shadcn-idiomatic way to hit WCAG 1.3.1 (Info and Relationships) without color-only cueing.
- **`noValidate` on `<form>`.** Disables the browser's native HTML5 validation so react-hook-form + zod own the entire error surface. Without this, users with modern browsers see two error tooltips (native + custom).
- **`Cmd+Enter` listener wired at `<form>`-level.** Scoped to this form; doesn't conflict with Cmd+K or any global hotkey. `event.preventDefault()` stops the default "add newline" behavior in the `<Textarea>`.
- **`void form.handleSubmit(onSubmit)()` pattern.** The double-invocation passes the form's current state through zodResolver, same as a click on the submit button. The `void` keyword silences a TS "floating promise" warning — the handler returns a Promise we don't need to await.
- **`mode: "onBlur"`.** Triggers validation when the field loses focus, not on every keystroke. Matches UX-DR40 exactly ("on-blur for format").

### File structure (target)

```
apps/web/
├── components.json                            # NEW — AC1
├── .prettierignore                            # MODIFIED (add src/components/ui/)
├── eslint.config.mjs                          # MODIFIED (ignore src/components/ui/**)
├── package.json                               # MODIFIED (new runtime + peer deps)
├── src/
│   ├── app/
│   │   └── globals.css                        # MODIFIED (shadcn @layer base block)
│   ├── components/
│   │   ├── forms/
│   │   │   ├── ExampleForm.tsx                # NEW — AC6
│   │   │   └── ExampleForm.test.tsx           # NEW — AC7
│   │   └── ui/                                # NEW (shadcn-generated; lint-ignored)
│   │       ├── accordion.tsx
│   │       ├── avatar.tsx
│   │       ├── badge.tsx
│   │       ├── button.tsx
│   │       ├── card.tsx
│   │       ├── collapsible.tsx
│   │       ├── command.tsx
│   │       ├── context-menu.tsx
│   │       ├── dialog.tsx
│   │       ├── dropdown-menu.tsx
│   │       ├── form.tsx
│   │       ├── hover-card.tsx
│   │       ├── input.tsx
│   │       ├── label.tsx
│   │       ├── popover.tsx
│   │       ├── progress.tsx
│   │       ├── scroll-area.tsx
│   │       ├── separator.tsx
│   │       ├── sheet.tsx
│   │       ├── sonner.tsx
│   │       ├── tabs.tsx
│   │       ├── textarea.tsx
│   │       └── tooltip.tsx
│   ├── lib/
│   │   └── utils.ts                           # NEW (shadcn cn() helper)
│   └── stories/
│       └── Foundations/
│           ├── Tokens.stories.tsx             # EXISTING (Story 1.4 — do not touch)
│           └── ButtonVariants.stories.tsx     # NEW — AC4

docs/
├── design-tokens.md                           # MODIFIED (shadcn bridge section now live)
├── repo-layout.md                             # MODIFIED ("What Story 1.5 shipped" + strike note)
└── shadcn.md                                  # NEW — AC21
```

---

## Testing Standards

- **Vitest + @testing-library/react** for `ExampleForm.test.tsx`. Run via `pnpm --filter @deployai/web test`; part of the root `pnpm test` / `pnpm turbo run test` graph (Story 1.4).
  - Happy-path submit: callback fires once with `{ email, message }`.
  - Required-field validation (message): `<FormMessage>` shows "Message is required"; `aria-invalid="true"` on the `<Textarea>`.
  - On-blur format validation (email): `<FormMessage>` shows "Enter a valid email" after blur; submit callback NOT fired.
  - Cmd+Enter submit: `user.keyboard("{Meta>}{Enter}{/Meta}")` triggers submission.
  - `aria-invalid` + `aria-describedby` wiring: both flip correctly as errors appear/resolve.
  - Label-above-input: every field's label is a visible `<label>` element above the input.
- **Storybook + @storybook/addon-a11y** for `ButtonVariants.stories.tsx`. Every story renders under axe-core with `runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]` (from Story 1.4 `preview.ts`). Zero violations required.
- **No snapshot tests.** Snapshots break on every dependency bump and the shadcn primitives change shape upstream; semantic queries are more resilient.
- **No unit tests for the shadcn primitives themselves.** Upstream owns those.
- **CI continuity:** `pnpm turbo run lint typecheck test build` stays at 20/20. `pnpm --filter @deployai/web build-storybook` continues to succeed.
- **Linter coverage:** `src/components/ui/**` is `globalIgnores`'d so shadcn-authored code doesn't trigger `@typescript-eslint/*` rules we'd otherwise never hit. Everything else in `apps/web/src/` remains under full lint.

---

## Source Hints

- **`_bmad-output/planning-artifacts/epics.md` lines 661–676** — Story 1.5 user story + ACs (the 23-primitive list is line 672; `UX-DR39` variant list is line 674; react-hook-form + zod + ExampleForm is line 675).
- **`_bmad-output/planning-artifacts/epics.md` lines 288–292, esp. 292** — UX-DR3 shadcn primitive set enumeration (matches our AC2 but lists Toast-via-sonner + TanStack-wrapped Table; Table is explicitly out of scope for 1.5 per AC24 and arrives in Story 1.16).
- **`_bmad-output/planning-artifacts/epics.md` lines 346, 347** — UX-DR39 (button hierarchy — 36 px min, 44×44 hit, `aria-label` on icon-only) and UX-DR40 (form patterns — label above, asterisk + text, on-blur format + on-submit completeness, `aria-invalid` + `aria-describedby`, Cmd+Enter submits).
- **`_bmad-output/planning-artifacts/ux-design-specification.md` lines 292–315** — Design system choice (why shadcn; code-ownership model — "copy-pasted into the codebase and owned by us" — is load-bearing for this story's scope fence).
- **`_bmad-output/planning-artifacts/ux-design-specification.md` lines 437–466** — Palette hex values (already captured by Story 1.4 tokens; this story reads them via tokens only, never by hex).
- **`_bmad-output/planning-artifacts/ux-design-specification.md` lines 726–747** — Foundation component list from shadcn/ui (matches AC2).
- **`_bmad-output/planning-artifacts/ux-design-specification.md` lines 827–853** — Component Architecture + Implementation Roadmap (Phase 1 Weeks 5–8 lands shadcn init + theme tokens — exactly this story).
- **`_bmad-output/planning-artifacts/ux-design-specification.md` lines 859–866** — Button Hierarchy detail (primary/secondary/ghost/destructive semantics).
- **`_bmad-output/planning-artifacts/ux-design-specification.md` lines 877–883** — Form Patterns detail (the source of truth for `ExampleForm.tsx`'s behavior).
- **`_bmad-output/planning-artifacts/ux-design-specification.md` lines 885–898** — Navigation, Feedback, Modal/Overlay patterns (context for why we install Sheet, Popover, Sonner, Dialog).
- **`_bmad-output/planning-artifacts/architecture.md` lines 127, 143** — Architectural decision: shadcn/ui init in `apps/web` via `pnpm dlx shadcn@latest init` (Tech Stack + Starter Template Evaluation).
- **`_bmad-output/planning-artifacts/prd.md` lines 1633–1635** — NFR42 (WAI-ARIA semantic structure), NFR43 (a11y-first design process), NFR44 (pre-V1 usability study). All reinforce "primitives must carry ARIA out of the box" — which is why we pick Radix-backed shadcn.
- **`_bmad-output/implementation-artifacts/1-4-design-tokens-package.md`** — Previous story; every token referenced in the theme-bridge snippet traces back to a token emitted by Story 1.4's `dist/tokens.css`.
- **`docs/design-tokens.md` lines 178–203** — The shadcn bridge plan. Story 1.5 turns that plan into shipping CSS.
- **`docs/repo-layout.md` lines 21, 126** — Post-Story-1.4 status ("Story 1.5 initializes shadcn/ui") and the "not yet contain" bullet ("No shadcn/ui init — Story 1.5") — both updated by AC22.
- **shadcn CLI v4 changelog (2026-03):** https://ui.shadcn.com/docs/changelog/2026-03-cli-v4
- **shadcn Tailwind v4 docs:** https://ui.shadcn.com/docs/tailwind-v4
- **shadcn components.json schema:** https://ui.shadcn.com/docs/components-json
- **@hookform/resolvers v5.2.2 release notes (Zod 4 support path):** https://github.com/react-hook-form/resolvers/releases

---

## Risks

1. **Lockfile thrash.** `pnpm dlx shadcn@latest add` mutates `apps/web/package.json` with a variable dep set depending on shadcn's upstream pins. The first `pnpm install --frozen-lockfile` after `shadcn add` will fail; the dev agent must regenerate the lockfile via `pnpm install` (no flag) then re-verify `--frozen-lockfile` cleanliness. **Mitigation:** Task Phase 2's last bullet explicitly calls this out.
2. **Radix peer-dep compatibility with React 19.2.** Radix packages (Dialog, DropdownMenu, Popover, etc.) took multiple releases across 2024–2025 to drop `forwardRef` warnings under React 19. As of 2026-04, the current Radix versions shadcn pins are React 19-clean — but if the dev agent sees `forwardRef is deprecated` warnings in the Storybook console, bump the Radix peer explicitly via `pnpm update @radix-ui/*@latest`. **Mitigation:** Dev Notes §Known gotchas #3 documents this path.
3. **shadcn CLI stable channel regresses on Tailwind v4.** Unlikely (CLI v4 shipped March 2026 explicitly for Tailwind v4), but if the dev agent hits template breakage, fall back to `shadcn@canary` and note the version in Dev Agent Record.
4. **Token-name collisions with shadcn defaults.** The shadcn CLI injects `:root { --primary: oklch(...); --radius: 0.625rem; ... }` directly in `globals.css`. If the dev agent doesn't **delete** the injected values and replace with `var(--color-…)` references (Phase 3), shadcn's OKLCH defaults will win the cascade and the bridge will silently fail. The ButtonVariants story will render as shadcn's default slate/white, not DeployAI's evidence-blue/paper. **Mitigation:** AC3's "no hardcoded hex, no direct hsl literals" is the hard gate; Storybook visual verification during Phase 3 catches this before CI.
5. **Form resolver type inference edge cases.** `@hookform/resolvers@5` changed the `useForm` generic signature to `useForm<Input, Context, Output>`. Passing `useForm<ExampleFormValues>()` without the proper `Input`/`Output` positional generics **works** but requires TS 5.x inference; if the dev agent opts to declare the generic explicitly, they must use the three-parameter form. **Mitigation:** The `ExampleForm.tsx` skeleton in Phase 5 uses `useForm<ExampleFormValues>({...})` which is the correct one-generic form; resolver v5's type inference fills in the other slots.
6. **Zod 4 vs Zod 3 schema syntax.** Zod v4 made minor breaking changes to error-map API + `z.string().email()` behavior. `@hookform/resolvers@5.2.2` supports both. The `ExampleForm.tsx` skeleton uses Zod v4 syntax (`.email("msg")` positional). If the dev agent sees a peculiar TS error on the error-map arg, double-check they're importing from `zod` (v4) and not `zod/v3`.
7. **`.prettierignore` drift.** If the dev agent adds `src/components/ui/**` only to `eslint.config.mjs` and forgets the Prettier side, a `pnpm format` run will rewrite every shadcn file and create a massive diff that conflicts with the next `shadcn add`. **Mitigation:** AC10 explicitly covers both ignores; Phase 4 verifies with `pnpm format:check`.
8. **Storybook + Next.js `"use client"` directives.** shadcn primitives that manage state (Dialog, Popover, DropdownMenu) have `"use client"` at the top of their generated files. In Storybook (which runs in Vite, not Next's server), this directive is a no-op — rendering works. But if `apps/web/.storybook/main.ts` ever switches framework (away from `@storybook/nextjs-vite`), client-directive handling may break. **Mitigation:** Note in `docs/shadcn.md` that `@storybook/nextjs-vite` is the officially-supported framework for this stack.
9. **Accessibility regressions via `<Button size="icon">`.** An icon-only button without `aria-label` fails axe-core `button-name`. The Storybook `ButtonVariants` stories must include an explicit icon-only case **with** `aria-label`. The dev agent should render this story in Storybook UI and confirm the a11y addon shows zero violations before committing. **Mitigation:** AC4 enumerates the icon-only case; Dev Notes §Known gotchas #8 repeats it.
10. **`next-themes` install surprise.** `next-themes` is a Sonner peer-dep (not a direct dep of our code). Without it, `pnpm add sonner` fails the peer check and pnpm exits non-zero. **Mitigation:** AC11 declares both sonner + next-themes explicitly; Phase 2's `shadcn add sonner` should resolve the peer automatically if the CLI does its job.
11. **Story 1.4 regression via `globals.css` edits.** The `@layer base :root` block Story 1.5 adds sits next to the `@import "@deployai/design-tokens/tokens.css"` the previous story set up. Accidentally removing the tokens import (or reordering it after the shadcn layer) breaks every `Tokens.stories.tsx` color swatch. **Mitigation:** AC17 requires Story 1.4's Tokens stories still pass; Phase 9 verification catches this.

---

## Previous Story Intelligence (from Story 1.4 that affects 1.5)

Story 1.4 landed the foundation Story 1.5 builds on. Critical inheritances:

- **`@deployai/design-tokens` dual-surface exports.** `apps/web` already consumes the package via `workspace:*`. `globals.css` already `@import`s both `@deployai/design-tokens/tailwind` (Tailwind v4 `@theme` preset) and `@deployai/design-tokens/tokens.css` (raw CSS custom properties). Story 1.5 reads these; it does not touch the tokens package.
- **Token names available to the bridge:**
  - Colors: `--color-ink-{400,600,800,950}`, `--color-paper-{100,200,300,400}`, `--color-stone-500`, `--color-evidence-{100,600,700}`, `--color-signal-{100,700}`, `--color-null-{100,600}`, `--color-destructive-{100,700}`.
  - Spacing: dual-emit `--space-{0…24}` + `--spacing-{0…24}` (Tailwind v4's dynamic `--spacing: 4px` base + per-step overrides).
  - Radii: `--radius-{none,sm,md,lg,full}`.
  - Shadows: `--shadow-{sm,md,lg,focus,none}`.
  - Focus shadow: `--shadow-focus: 0 0 0 2px paper[100], 0 0 0 4px evidence[700]` (Review Finding applied post-PR #4).
  - Typography: dual-surface — semantic (`--font-family-sans`, `--text-body-size`, `--text-body-line-height`) **and** Tailwind-v4-idiomatic (`--font-sans`, `--font-mono`, `--text-body`, `--text-body--line-height`). Story 1.5 uses the Tailwind-v4 names.
  - next/font variables: `--font-inter` (Inter from `next/font/google`), `--font-ibm-plex-mono` (IBM Plex Mono from `next/font/google`), wired on `<html>` in `layout.tsx`. `--font-sans` / `--font-mono` in tokens reference these.
  - Motion: `--duration-{instant,reduced-motion,fast,base}`, `--easing-{standard,out}`.
  - Elevation: `--elevation-{base,raised,overlay,dropdown,modal,toast}`.
- **Story 1.4 Review Findings applied (carry-forwards for 1.5):**
  - `ink-400` is now `#6A6E78` (was `#737780`; measured 4.95:1 on paper-100 — clears WCAG AA body-text 4.5:1 floor). Story 1.5 does not need to re-test, but the bridge can trust `ink-400` as body-text safe.
  - `paper-400` is **decorative-only**. The `packages/design-tokens/src/colors.ts#paper` comment explicitly forbids using it for form borders, focus rings, toggles, or any actionable UI chrome (it fails the 3:1 non-text floor against paper-100). This is why `--border` in Story 1.5's bridge maps to `paper-300` and `--input` maps to `stone-500`, not `paper-400`.
  - Shadow focus ring: `0 0 0 2px paper[100], 0 0 0 4px evidence[700]`. Story 1.5's `--ring: var(--color-evidence-700)` aligns with this color so DOM `outline`-based focus + `box-shadow`-based focus agree.
- **Storybook 10.3 (`@storybook/nextjs-vite`) already set up in `apps/web`.**
  - `apps/web/.storybook/main.ts`: framework `@storybook/nextjs-vite`, addons `@storybook/addon-a11y` + `@storybook/addon-docs`, story globs `../src/**/*.mdx` + `../src/**/*.stories.@(ts|tsx)`, `staticDirs: ["../public"]`, `typescript.reactDocgen: "react-docgen"` (enabled — required for autodocs prop tables).
  - `apps/web/.storybook/preview.ts`: imports `../src/app/globals.css`, enables `tags: ["autodocs"]`, and configures a11y addon with `runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]` (expanded from Story 1.4 review to cover SC 1.4.11 non-text contrast + SC 2.5.5/2.5.8 target sizes).
- **Turbo graph:** `build-storybook` is a first-class Turbo task (`turbo.json#build-storybook`, depends on `^build`, outputs `storybook-static/**`). Story 1.5's new Storybook stories automatically flow into `pnpm turbo run build-storybook`.
- **ESLint flat-config pattern for `apps/web`:** `defineConfig([ ...nextVitals, ...nextTs, globalIgnores([...]) ])`. Story 1.5 extends `globalIgnores` with `src/components/ui/**`; nothing else in the config changes.
- **`.prettierignore` already covers `**/storybook-static/`** (Story 1.3 inherits). Story 1.5 appends `src/components/ui/` for shadcn-authored code.
- **Vitest setup in `apps/web`.** `vitest` config is minimal (`--passWithNoTests` dropped in Story 1.4 for `packages/design-tokens`; `apps/web` still has `--passWithNoTests` because Story 1.3's `page.test.tsx` is the only test; Story 1.5 adds `ExampleForm.test.tsx` which guarantees non-empty). The existing devDeps (`@testing-library/react`, `@testing-library/jest-dom`, `jsdom`, `@vitejs/plugin-react`) are sufficient; we add `@testing-library/user-event` if not already present (check `apps/web/package.json`; v14 is the current stable).
- **No hardcoded colors / spacing / fonts anywhere in `apps/web/src/`.** Story 1.4's AC4 + AC16 enforced this. Story 1.5 continues the discipline — every concrete value in the shadcn bridge flows from a token.
- **`apps/web/src/app/globals.css` structure (current, post-1.4):** `@import "tailwindcss"` → `@import "@deployai/design-tokens/tailwind"` → `@import "@deployai/design-tokens/tokens.css"` → `html, body` base rule → `code, kbd, samp, pre` base rule → `@media (prefers-reduced-motion: reduce)` block. Story 1.5 appends a new `@layer base { :root { ... } }` block AFTER the tokens imports (ordering matters — the bridge references tokens, so tokens must be loaded first). The CLI may inject additional lines like `@plugin "tw-animate-css"`; preserve them.

---

## Dev Agent Record

### Agent Model Used

_(to be filled by the dev agent)_

### Debug Log References

_(to be filled by the dev agent — capture: CLI output from `shadcn@latest init`, CLI output from the batched `shadcn add`, lockfile regeneration path, any Radix / React 19 peer-dep warnings, any OKLCH values the CLI left behind that needed scrubbing, any axe-core violations the ButtonVariants stories surfaced on first render.)_

### Completion Notes List

_(to be filled by the dev agent — per-AC "satisfied by X" notes, intentional deviations from the story context, any findings that should feed a future review.)_

### File List

_(to be filled by the dev agent during implementation — prospective list below.)_

**New files:**

- `apps/web/components.json`
- `apps/web/src/lib/utils.ts`
- `apps/web/src/components/ui/accordion.tsx`
- `apps/web/src/components/ui/avatar.tsx`
- `apps/web/src/components/ui/badge.tsx`
- `apps/web/src/components/ui/button.tsx`
- `apps/web/src/components/ui/card.tsx`
- `apps/web/src/components/ui/collapsible.tsx`
- `apps/web/src/components/ui/command.tsx`
- `apps/web/src/components/ui/context-menu.tsx`
- `apps/web/src/components/ui/dialog.tsx`
- `apps/web/src/components/ui/dropdown-menu.tsx`
- `apps/web/src/components/ui/form.tsx`
- `apps/web/src/components/ui/hover-card.tsx`
- `apps/web/src/components/ui/input.tsx`
- `apps/web/src/components/ui/label.tsx`
- `apps/web/src/components/ui/popover.tsx`
- `apps/web/src/components/ui/progress.tsx`
- `apps/web/src/components/ui/scroll-area.tsx`
- `apps/web/src/components/ui/separator.tsx`
- `apps/web/src/components/ui/sheet.tsx`
- `apps/web/src/components/ui/sonner.tsx`
- `apps/web/src/components/ui/tabs.tsx`
- `apps/web/src/components/ui/textarea.tsx`
- `apps/web/src/components/ui/tooltip.tsx`
- `apps/web/src/components/forms/ExampleForm.tsx`
- `apps/web/src/components/forms/ExampleForm.test.tsx`
- `apps/web/src/stories/Foundations/ButtonVariants.stories.tsx`
- `docs/shadcn.md`

**Modified files:**

- `apps/web/src/app/globals.css` (append `@layer base :root` block with shadcn semantic aliases mapped to tokens; delete any OKLCH / HSL / hex values the CLI injected; delete any `.dark { ... }` block the CLI injected)
- `apps/web/package.json` (new runtime deps: `@hookform/resolvers`, `@radix-ui/*` set, `class-variance-authority`, `clsx`, `cmdk`, `lucide-react`, `next-themes`, `react-hook-form`, `sonner`, `tailwind-merge`, `tw-animate-css`, `zod`; optional `"ui:add"` script)
- `apps/web/eslint.config.mjs` (add `src/components/ui/**` to `globalIgnores`)
- `apps/web/.prettierignore` **or** root `.prettierignore` (add `apps/web/src/components/ui/`)
- `docs/design-tokens.md` (replace pseudo-snippet in the shadcn bridge section with shipped CSS; add link to `docs/shadcn.md`)
- `docs/repo-layout.md` (append "What Story 1.5 shipped" section; strike `No shadcn/ui init — Story 1.5.` from the "not yet contain" list)
- `pnpm-lock.yaml` (regenerated for the new deps)

---

## Change Log

| Date       | Author | Summary |
|------------|--------|---------|
| 2026-04-22 | bmad-create-story (Kenny + context engine, claude-opus-4.7) | Initial comprehensive story context authored. Loaded `epics.md#Story-1.5` (lines 661–676), `ux-design-specification.md` §Foundations (437–531), §Component Architecture (827–853), §Button Hierarchy (859–866), §Form Patterns (877–883), §Navigation/Feedback/Modal Patterns (885–898), `architecture.md` §Starter Template (127, 143), `prd.md` NFR42/43/44 (1633–1635), Story 1.4 implementation artifact (file layout, dual-surface exports, review-finding carry-forwards — ink-400 to `#6A6E78`, paper-400 decorative-only, focus ring composition, dual-emit spacing, Tailwind-v4 font name alignment), `apps/web` current state (globals.css with tokens imports + prefers-reduced-motion, layout.tsx with next/font Inter + IBM Plex Mono, Storybook 10.3 `@storybook/nextjs-vite` + addon-a11y with wcag2a + wcag2aa + wcag21aa + wcag22aa matchers + reactDocgen enabled, eslint flat-config with `storybook-static/**` ignore, turbo first-class `build-storybook` task), `docs/design-tokens.md#shadcn bridge` pseudo-snippet. Researched latest stable via WebSearch (2026-04-22): shadcn/cli **v4** shipped March 2026 (stable supports Tailwind v4 + React 19 — no `@canary` required); `components.json` schema for v4 (`style: "new-york"` — default deprecated; `tailwind.config: ""` blank for v4; `baseColor: "neutral"`; `cssVariables: true`; `rsc: true`; `iconLibrary: "lucide"`); `react-hook-form@^7.73.1` + `zod@^4.3.6` + `@hookform/resolvers@^5.2.2` (v5.1+ supports Zod 4 natively via `/zod` path); `class-variance-authority@^0.7.1`, `clsx@^2.1.1`, `tailwind-merge@^3.5.0`, `cmdk@^1.1.1`, `sonner@^2.0.7`, `next-themes@^0.4.6` (Sonner peer), `tw-animate-css@^1.4.0` (Tailwind v4 replacement for deprecated `tailwindcss-animate`), `lucide-react@^0.468+` (drops forwardRef under React 19). Captured 24 ACs (7 epic-source + 17 cross-cutting covering components.json schema, 23-primitive core set enumeration, theme-bridge snippet, ButtonVariants story matrix, react-hook-form + zod + ExampleForm, Vitest coverage shape, ESLint/Prettier ignore for shadcn-generated code, doc deliverables, turbo graph continuity, scope-fence). 10 task phases, 75+ subtasks. Dev Notes cover shadcn CLI v4 Tailwind v4 status, style=new-york + baseColor=neutral rationale, theme bridge design (two-layer cascade), concrete bridging snippet with per-variable rationale (paper-300 for `--border` because paper-400 is decorative-only; stone-500 for `--input` because it clears 3:1 non-text; evidence-700 for `--ring` to align with tokens `--shadow-focus`), 7 anti-patterns (don't let CLI OKLCH survive; don't install outside the 23-primitive set; don't fork primitives; don't hand-add cva/clsx/tailwind-merge; don't auto-render Toaster; don't wrap in ThemeProvider; don't touch `ui/*.tsx`), 11 known gotchas (CLI-injected `:root` overwrite; Sonner `next-themes` peer; lucide-react + React 19 forwardRef; rhf v7 `Controller` vs `register` for composites; Cmd+Enter form-scoped vs global; `rsc: true` + `"use client"`; `@theme inline` vs non-inline; icon-only a11y-label; `FormMessage` empty-description behavior; `ui/*.tsx` re-generation churn; flat-config `globalIgnores` vs `ignores`), testing strategy (Vitest + RTL semantic queries, Storybook + axe-core for button matrix, no snapshots, no unit tests for shadcn primitives themselves), `ExampleForm.tsx` design rationale (two-field schema exercising both on-blur format + on-submit completeness; asterisk + sr-only "required"; `noValidate`; form-scoped Cmd+Enter; `mode: "onBlur"`), 11 risks (lockfile thrash, Radix/React 19 compat, CLI regression fallback, token-name collisions, resolver type inference, Zod 4 syntax, .prettierignore drift, Storybook client-directive, icon-only a11y regression, next-themes peer surprise, Story 1.4 regression via globals.css), and full Previous Story Intelligence (every token name, storybook config shape, turbo graph, lint/prettier ignore pattern, review-finding carry-forwards, globals.css structure post-1.4). File list enumerates 29 new files + 7 modified. Status → ready-for-dev. |

### Open Questions

_(saved for the implementing dev agent and/or a follow-up review round.)_

1. **Root `.prettierignore` vs `apps/web/.prettierignore` placement.** The repo currently appears to have a root `.prettierignore` but no workspace-local one. If the dev agent discovers a workspace-local Prettier config exists, prefer that placement for the `src/components/ui/` ignore; otherwise append to the root file. Either satisfies AC20; neither breaks the build.
2. **`"ui:add"` convenience script.** AC13 marks this as optional. If the dev agent skips it, no CI/test regression occurs — future primitive additions just require typing the longer `pnpm dlx shadcn@latest add <name>` command. Recommended to include for documentation value.
3. **Sonner placement in layout.** The scope fence (AC24 bullet 5) explicitly defers the `<Toaster />` mount to the first toast consumer. If the dev agent feels strongly about mounting it preemptively in `layout.tsx` (so future stories don't need to touch root layout), they should raise this via checkpoint review rather than silently reverting the scope-fence decision. The cost of preemptive mount is: an invisible overlay DOM node on every route; the benefit is: no layout.tsx edit in the first toast consumer's story.
4. **Next-themes provider.** Same tension as #3 — installing `next-themes` as a Sonner peer but **not** wrapping `<ThemeProvider>` means if the dev agent ever wants light/dark toggling pre-Epic 7, they'll need to revisit this decision. The V1-is-light-only stance (`ux-design-specification.md` line 468) makes the decision for Story 1.5, but note this trade-off in Dev Agent Record if discovered.
5. **Should `packages/shared-ui/` land as an empty stub in Story 1.5 to stabilize the `packages/*` pattern?** AC24 explicitly defers this. The argument for landing it empty now: Epic 7's first composite (CitationChip) has a clearer home. The argument against: empty stubs bloat Turbo and make the repo look more complete than it is. Current guidance: **no** — keep the scope fence tight, Epic 7 adds `packages/shared-ui/` as part of its first composite story.
