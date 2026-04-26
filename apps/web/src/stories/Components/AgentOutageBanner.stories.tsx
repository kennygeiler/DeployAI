import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { AgentOutageBanner } from "@deployai/shared-ui";

const meta: Meta<typeof AgentOutageBanner> = {
  title: "Components/AgentOutageBanner",
  component: AgentOutageBanner,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof AgentOutageBanner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Informational: Story = {
  args: {
    agentName: "Cartographer",
    message:
      "Ingestion is ~15 seconds behind. In-meeting retrievals may include slightly older transcript context.",
    variant: "informational",
    statusPageUrl: "https://status.example.com",
    retryAvailable: true,
    onRetry: () => {},
  },
};

export const Alert: Story = {
  args: {
    agentName: "Oracle",
    message: "Retrieval is unavailable. Operating in memory-only mode until service recovers.",
    variant: "alert",
    statusPageUrl: "https://status.example.com",
    etaText: "ETA ~5 min",
  },
};

export const Resolved: Story = {
  args: {
    agentName: "All agents",
    message: "All systems within SLO. You can resume normal workflows.",
    variant: "resolved",
  },
};
