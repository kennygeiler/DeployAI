import type { Preview } from "@storybook/nextjs-vite";
import { MINIMAL_VIEWPORTS } from "storybook/viewport";

import "../src/app/globals.css";
import { AXE_WCAG_TAGS } from "../src/lib/a11y-config";

/**
 * UX-DR37 / Story 7-13 — viewports aligned with `epics.md` (mobile default, tablet `md:` band,
 * laptop `lg:`, desktop `xl` / content max). Storybook 10 ships the toolbar module from
 * `storybook/viewport` (no separate `@storybook/addon-viewport` package).
 */
const EPIC7_VIEWPORTS = {
  ...MINIMAL_VIEWPORTS,
  deployaiMobile360: {
    name: "Epic7 mobile (360×740)",
    styles: { width: "360px", height: "740px" },
    type: "mobile" as const,
  },
  deployaiTablet820: {
    name: "Epic7 tablet (820×1180)",
    styles: { width: "820px", height: "1180px" },
    type: "tablet" as const,
  },
  deployaiLaptop1100: {
    name: "Epic7 laptop (1100×800)",
    styles: { width: "1100px", height: "800px" },
    type: "desktop" as const,
  },
  deployaiDesktop1440: {
    name: "Epic7 desktop (1440×900)",
    styles: { width: "1440px", height: "900px" },
    type: "desktop" as const,
  },
};

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
        // Story 1.6 AC9: axe WCAG tag list from `src/lib/a11y-config.ts` — same constant as
        // test-runner + Playwright + @axe-core/react (Story 7.14: every story is axe-gated in CI).
        runOnly: [...AXE_WCAG_TAGS],
      },
    },
    viewport: {
      options: EPIC7_VIEWPORTS,
    },
    /** Story 7-13 / Chromatic — visual snapshots at Tailwind-aligned widths (see `BREAKPOINT_PX`). */
    chromatic: {
      viewports: [360, 768, 1024, 1280, 1440],
    },
    docs: {
      description: {
        component:
          "**Keyboard (Epic 7.14):** Tab / Shift+Tab traverse focus in DOM order; Space / Enter activate buttons and toggles; Esc closes overlays where Radix applies it.\n\n" +
          "**Screen reader:** Stories render production-like semantics (`aria-*`, headings, landmarks). Verify with VoiceOver (macOS/iOS) or NVDA (Windows) against the same strings operators hear in `apps/web`.\n\n" +
          "**Viewports:** Use the Storybook viewport toolbar (UX-DR37–38). Chromatic (when enabled) snapshots the `chromatic.viewports` widths on each story.",
      },
    },
  },
  initialGlobals: {
    viewport: { value: "deployaiDesktop1440", isRotated: false },
  },
  tags: ["autodocs"],
};

export default preview;
