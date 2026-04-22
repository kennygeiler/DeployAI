import type { Preview } from "@storybook/nextjs-vite";

import "../src/app/globals.css";
import { AXE_WCAG_TAGS } from "../src/lib/a11y-config";

const preview: Preview = {
  parameters: {
    layout: "centered",
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    a11y: {
      options: {
        // Story 1.6 AC9: axe WCAG tag list is now sourced from
        // src/lib/a11y-config.ts — same constant the Storybook
        // test-runner, Playwright E2E specs, and @axe-core/react dev
        // runtime import. Covers WCAG 2.0 AA + WCAG 2.1 AA (adds SC
        // 1.4.11 non-text contrast, 1.4.13 content-on-hover, 2.5.5
        // target size) + WCAG 2.2 AA (2.4.11 focus not obscured, 2.5.8
        // target size min) so the addon catches the same floors the
        // tokens.test.ts contrast suite claims.
        runOnly: [...AXE_WCAG_TAGS],
      },
    },
  },
  tags: ["autodocs"],
};

export default preview;
