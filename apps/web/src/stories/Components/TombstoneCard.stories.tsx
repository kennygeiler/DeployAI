import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { TombstoneCard } from "@deployai/shared-ui";

const meta: Meta<typeof TombstoneCard> = {
  title: "Components/TombstoneCard",
  component: TombstoneCard,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
} satisfies Meta<typeof TombstoneCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Final: Story = {
  args: {
    retentionReason: "Superseded by policy T-2: 90-day rolling window for draft learnings.",
    destroyedAt: "2026-01-10T12:00:00Z",
    originalNodeId: "a1b2c3d4-aaaa-bbbb-cccc-ddddeeee0001",
    authorityActor: "tenant-security@agency.gov",
    rfc3161Verified: true,
    appealAvailable: false,
  },
};

export const WithAppeal: Story = {
  args: {
    ...Final.args,
    appealAvailable: true,
    onAppeal: () => {},
  },
};
