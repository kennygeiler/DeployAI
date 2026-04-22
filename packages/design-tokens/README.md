# @deployai/design-tokens

Single source of truth for DeployAI's design tokens — colors, spacing, typography,
shadows, radii, and elevation. Satisfies `UX-DR1` and `UX-DR2`.

Consumed from TypeScript (`import { colors, spacing } from "@deployai/design-tokens"`),
raw CSS custom properties (`@import "@deployai/design-tokens/tokens.css"`), or as a
Tailwind v4 `@theme` preset (`@import "@deployai/design-tokens/tailwind"`).

See [`docs/design-tokens.md`](../../docs/design-tokens.md) for the rationale behind
the palette, the 4 px spacing ladder, the Inter + IBM Plex Mono type ramp, and the
WCAG AA contrast methodology.

## Scripts

| Command            | Behavior                                                     |
| ------------------ | ------------------------------------------------------------ |
| `pnpm build`       | `tsc` → `dist/index.js` + `.d.ts`, then emit CSS bundles     |
| `pnpm lint`        | Flat ESLint (`--max-warnings 0`)                             |
| `pnpm typecheck`   | `tsc --noEmit`                                               |
| `pnpm test`        | Vitest (contrast + CSS-variable invariants)                  |
| `pnpm clean`       | Remove `dist/` and `node_modules/`                           |

No runtime dependencies — the package is pure token data.
