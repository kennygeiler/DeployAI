import type { Preview } from "@storybook/nextjs-vite";

import "../src/app/globals.css";

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
        // Run axe-core against every story by default; UX-DR34's CI-blocking
        // gate lands in Story 1.6. Cover WCAG 2.0 AA + WCAG 2.1 AA (adds
        // SC 1.4.11 non-text contrast, 1.4.13 content-on-hover, 2.5.5 target
        // size) + WCAG 2.2 AA (2.4.11 focus not obscured, 2.5.8 target size
        // min) so the addon catches the same floors the tokens.test.ts
        // contrast suite claims.
        runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"],
      },
    },
  },
  tags: ["autodocs"],
};

export default preview;
