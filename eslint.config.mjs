import js from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: [
      "node_modules/",
      ".turbo/",
      "**/dist/",
      "**/build/",
      "**/.next/",
      "**/target/",
      "**/storybook-static/",
      "pnpm-lock.yaml",
    ],
  },
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: { ...globals.node },
    },
  },
];
