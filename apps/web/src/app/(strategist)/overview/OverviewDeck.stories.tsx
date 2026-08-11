import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { OverviewDeck } from "./OverviewDeck.client";

/**
 * Product overview deck (/overview) — the slide-deck walkthrough of the
 * strategist surfaces. The screenshots load from `public/overview/*`
 * (Storybook serves `public/` as a static dir), captured against the seeded
 * BlueState engagements by `scripts/capture-overview.mjs`.
 */
const meta = {
  title: "Overview/OverviewDeck",
  component: OverviewDeck,
  parameters: {
    layout: "fullscreen",
  },
} satisfies Meta<typeof OverviewDeck>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
