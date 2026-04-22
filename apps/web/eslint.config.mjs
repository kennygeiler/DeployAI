import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "storybook-static/**",
    "node_modules/**",
    "coverage/**",
    "next-env.d.ts",
    // shadcn-authored primitive files — treated as vendored third-party code
    // so future `pnpm dlx shadcn@latest add` regenerations stay diff-clean.
    // See docs/shadcn.md for the full rationale.
    "src/components/ui/**",
  ]),
]);

export default eslintConfig;
