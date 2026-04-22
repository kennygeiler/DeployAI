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
        // gate lands in Story 1.6.
        runOnly: ["wcag2a", "wcag2aa"],
      },
    },
  },
  tags: ["autodocs"],
};

export default preview;
