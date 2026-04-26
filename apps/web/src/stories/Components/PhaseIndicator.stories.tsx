import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { PhaseIndicator, type PhaseIndicatorProps } from "@deployai/shared-ui";

const meta: Meta<typeof PhaseIndicator> = {
  title: "Components/PhaseIndicator",
  component: PhaseIndicator,
  tags: ["autodocs"],
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Top-left deployment phase chrome (UX-DR6). Open the popover to review all seven " +
          "phases; changes announce with aria-live. Epic 5.4 state machine IDs.",
      },
    },
  },
  argTypes: {
    currentPhaseId: { control: "select" },
    variant: { control: "select" },
  },
} satisfies Meta<typeof PhaseIndicator>;

export default meta;
type Story = StoryObj<typeof meta>;

const ids = [
  "P1_pre_engagement",
  "P2_discovery",
  "P3_ecosystem_mapping",
  "P4_design",
  "P5_pilot",
  "P6_scale",
  "P7_inheritance",
] as const satisfies readonly PhaseIndicatorProps["currentPhaseId"][];

function InteractivePhase(props: Omit<PhaseIndicatorProps, "currentPhaseId">) {
  const [ix, setIx] = useState(4);
  return (
    <div className="flex flex-col items-start gap-4">
      <PhaseIndicator currentPhaseId={ids[ix]!} {...props} />
      <p className="text-body text-ink-600 max-w-md">
        Dev control (Storybook only): change phase to hear the polite live announcement.
      </p>
      <div className="flex flex-wrap gap-2">
        {ids.map((id, i) => (
          <Button
            key={id}
            type="button"
            variant="outline"
            size="xs"
            className="text-body border-border bg-paper-100 font-mono"
            onClick={() => {
              setIx(i);
            }}
          >
            {id.replace(/_/g, " ")}
          </Button>
        ))}
      </div>
    </div>
  );
}

export const Default: Story = {
  args: { currentPhaseId: "P5_pilot", variant: "default" },
};

export const PendingTransition: Story = {
  args: { currentPhaseId: "P4_design", variant: "pending-transition" },
};

export const Locked: Story = {
  args: { currentPhaseId: "P6_scale", variant: "locked" },
};

export const Interactive: Story = {
  render: () => <InteractivePhase variant="default" />,
  parameters: { layout: "padded" },
};
