import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { SessionBanner } from "@deployai/shared-ui";

const future = (s: number) => Date.now() + s * 1000;

const meta: Meta<typeof SessionBanner> = {
  title: "Components/SessionBanner",
  component: SessionBanner,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof SessionBanner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const BreakGlass: Story = {
  args: {
    sessionId: "bg-7b2a9c1e-0001-4000-8000-abcdef001122",
    variant: "break-glass",
    expiresAt: future(45 * 60),
  },
};

export const ExternalAuditor: Story = {
  args: {
    sessionId: "aud-1a2b3c4d-5566-7788-99aa-bbccddeeff00",
    variant: "external-auditor",
    expiresAt: future(120 * 60),
  },
};
