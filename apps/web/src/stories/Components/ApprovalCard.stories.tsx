import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";

import { ApprovalCard } from "@/components/ui/approval-card";

/**
 * Components / ApprovalCard — Beautiful UI component 04. Human-in-the-loop
 * question card: the agent proposes options and waits for accept/decline.
 * Presentational only — selection and submission are callback-driven; the
 * HITL wiring (Oracle approval frames) lands in a later ticket.
 */
const meta = {
  title: "Components/ApprovalCard",
  component: ApprovalCard,
  tags: ["autodocs"],
} satisfies Meta<typeof ApprovalCard>;

export default meta;
type Story = StoryObj<typeof meta>;

const baseArgs = {
  question: "How many engagements should this proposal touch?",
  options: [
    { id: "core", label: "Three (core set)", description: "Only engagements with active members" },
    { id: "full", label: "Five (full portfolio)" },
    { id: "hero", label: "Just the flagship" },
  ],
};

function InteractiveApprovalCard() {
  const [selectedId, setSelectedId] = useState<string | null>("core");
  return (
    <div className="max-w-sm">
      <ApprovalCard
        {...baseArgs}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onAccept={(id) => console.info("accepted", id)}
        onDecline={() => console.info("declined")}
      />
    </div>
  );
}

export const Interactive: Story = {
  args: baseArgs,
  render: () => <InteractiveApprovalCard />,
};

export const Unselected: Story = {
  args: baseArgs,
  render: (args) => (
    <div className="max-w-sm">
      <ApprovalCard {...args} />
    </div>
  ),
};

export const Disabled: Story = {
  args: { ...baseArgs, disabled: true, selectedId: "full" },
  render: (args) => (
    <div className="max-w-sm">
      <ApprovalCard {...args} />
    </div>
  ),
};
