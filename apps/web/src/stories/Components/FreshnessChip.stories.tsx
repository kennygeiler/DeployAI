import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useEffect, useState } from "react";

import { FreshnessChip, type FreshnessSurface } from "@deployai/shared-ui";

const meta: Meta<typeof FreshnessChip> = {
  title: "Components/FreshnessChip",
  component: FreshnessChip,
  tags: ["autodocs"],
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Memory-sync altimeter (UX-DR7, NFR5). Bands come from `FRESHNESS_NFR5_MS` per surface " +
          "or custom `thresholdsMs`. Uses color + glyph + text (not color-only). " +
          "Use Storybook’s color-blind preview to verify contrast patterns.",
      },
    },
  },
} satisfies Meta<typeof FreshnessChip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const DigestSurface: Story = {
  args: {
    lastSyncedAt: Date.now() - 4 * 60 * 1000,
    surface: "digest" satisfies FreshnessSurface,
    tickMs: 60_000,
  },
};

export const InMeetingSurface: Story = {
  args: {
    lastSyncedAt: Date.now() - 45 * 1000,
    surface: "in_meeting",
    tickMs: 60_000,
  },
};

export const Unavailable: Story = {
  args: { lastSyncedAt: null },
};

function DriftDemo() {
  const [ts, setTs] = useState(() => Date.now() - 30 * 1000);
  useEffect(() => {
    const id = window.setInterval(() => {
      setTs((t) => t - 30_000);
    }, 3000);
    return () => window.clearInterval(id);
  }, []);
  return (
    <div className="max-w-md text-left">
      <p className="text-body text-ink-600 mb-3">
        Demo: timestamp drifts further into the past every 3s (for Storybook only) to exercise state
        transitions. Motion: respect OS “reduce motion” in the real app.
      </p>
      <FreshnessChip lastSyncedAt={ts} surface="phase_tracking" tickMs={1000} />
    </div>
  );
}

export const DriftInteractive: Story = {
  render: () => <DriftDemo />,
  parameters: { layout: "padded" },
};
