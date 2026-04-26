import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import jsxA11y from "eslint-plugin-jsx-a11y";

// Story 1.6: accessibility CI gate stack.
//
// `eslint-config-next` already registers `eslint-plugin-jsx-a11y` and
// enables a subset of its rules. We reinforce that by applying the
// plugin's recommended preset's full rule-map (with its per-rule option
// objects preserved — e.g. `no-interactive-element-to-noninteractive-role`'s
// element map) via a spread of `jsxA11y.flatConfigs.recommended.rules`.
// We deliberately do NOT re-register `plugins: { "jsx-a11y": jsxA11y }`
// here, because Next's flat config already did — redefining a plugin in
// a second block is a hard error in flat config.
//
// The recommended preset (v6.10.2) ships 34 rules — all either at
// `error` or intentionally `off` (`anchor-ambiguous-text`,
// `control-has-associated-label`, `label-has-for`). Zero rules ship at
// `warn`, so AC1's "every rule at error" is satisfied by the preset
// directly. This block comes AFTER `...nextVitals` / `...nextTs` so our
// severity wins any cascade conflict (flat-config: last-match-wins on
// severity for the same file). Scope is `src/**/*.{ts,tsx,jsx}`; the
// vendored shadcn tree (`src/components/ui/**`) is already covered by
// `globalIgnores` below and upstream owns its a11y posture.
//
// Appeal process: see docs/a11y-gates.md §Appeal process before adding
// any `eslint-disable-next-line jsx-a11y/*` — inline rationale + linked
// issue required.
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["src/**/*.{ts,tsx,jsx}"],
    rules: {
      ...jsxA11y.flatConfigs.recommended.rules,
      // Story 7.12 (UX-DR39): app code must use shadcn Button; primitives live
      // under `src/components/ui` which is not linted (see globalIgnores).
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXOpeningElement[name.name='button']",
          message:
            "Use <Button> from @/components/ui/button instead of a raw <button> (see docs/design-system/governance.md).",
        },
      ],
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "storybook-static/**",
    "node_modules/**",
    "coverage/**",
    "next-env.d.ts",
    "playwright-report/**",
    "test-results/**",
    // shadcn-authored primitive files — treated as vendored third-party code
    // so future `pnpm dlx shadcn@latest add` regenerations stay diff-clean.
    // See docs/shadcn.md for the full rationale.
    "src/components/ui/**",
  ]),
]);

export default eslintConfig;
