import type { StorybookConfig } from "@storybook/nextjs-vite";

const config: StorybookConfig = {
  stories: ["../src/**/*.mdx", "../src/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-a11y", "@storybook/addon-docs"],
  framework: {
    name: "@storybook/nextjs-vite",
    options: {},
  },
  staticDirs: ["../public"],
  typescript: {
    check: false,
    // `addon-docs` + `tags: ["autodocs"]` in preview.ts expect docgen metadata
    // to render prop tables; leave the default `react-docgen` parser enabled.
    reactDocgen: "react-docgen",
  },
};

export default config;
