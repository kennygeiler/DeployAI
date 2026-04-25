import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";

import { CitationChip, type CitationPreview, type CitationVisualState } from "@deployai/shared-ui";

const preview: CitationPreview = {
  citationId: "2d4437ee-9336-441e-ab57-121b81ee57a4",
  retrievalPhase: "P4 — Production (deploy window)",
  confidence: "0.94 (high agreement)",
  signedTimestamp: "2026-04-23T07:11:00.000Z",
};

function ChipShell({
  label,
  visualState = "default",
  variant = "inline",
  disableExpand = false,
}: {
  label: string;
  visualState?: CitationVisualState;
  variant?: "inline" | "standalone" | "compact";
  disableExpand?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <CitationChip
      label={label}
      expanded={expanded}
      onToggleExpand={() => {
        setExpanded((e) => !e);
      }}
      visualState={visualState}
      variant={variant}
      disableExpand={disableExpand}
      preview={preview}
      onViewEvidence={() => {}}
      onOverride={() => {}}
      onCopyLink={() => {}}
      onCiteInOverride={() => {}}
    />
  );
}

const meta: Meta<typeof CitationChip> = {
  title: "Components/CitationChip",
  component: CitationChip,
  tags: ["autodocs"],
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Signature citation primitive (Epic 7, Story 7-1, UX-DR4). " +
          "Chromatic baselines and governance live under Story 7-14. " +
          "Keyboard: Tab to focus, Enter/Space to expand/collapse, Esc to collapse when the chip is focused, " +
          "right-click for the context menu. Screen reader: full citation metadata is read via `aria-label` on the button.",
      },
    },
  },
} satisfies Meta<typeof CitationChip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => <ChipShell label="07:11 DOT standup" />,
};

export const Expanded: Story = {
  name: "Expanded (set via story state)",
  render: function Render() {
    const [expanded, setExpanded] = useState(true);
    return (
      <CitationChip
        label="10:03 same thread"
        expanded={expanded}
        onToggleExpand={() => {
          setExpanded((e) => !e);
        }}
        visualState="default"
        variant="inline"
        preview={preview}
        onViewEvidence={() => {}}
        onOverride={() => {}}
        onCopyLink={() => {}}
        onCiteInOverride={() => {}}
      />
    );
  },
};

export const Overridden: Story = {
  render: () => <ChipShell label="Prior week estimate" visualState="overridden" />,
};

export const Tombstoned: Story = {
  render: () => <ChipShell label="Removed budget line" visualState="tombstoned" />,
};

export const Compact: Story = {
  render: () => (
    <div className="max-w-md">
      <ChipShell label="Table row" variant="compact" />
    </div>
  ),
};

export const AllVariants: Story = {
  name: "Matrix — default / compact / states",
  render: () => (
    <div className="flex max-w-2xl flex-col gap-4 p-4 font-sans text-sm text-foreground">
      <p>
        <strong>Keyboard</strong> — Tab to each chip; Enter/Space toggles; Esc collapses;
        right-click for menu (View evidence, Override, Copy link, Cite in override).
      </p>
      <p className="text-muted-foreground">
        <strong>Screen reader</strong> — each chip exposes a single
        <code className="mx-1 rounded-sm bg-paper-200 px-1">button</code>
        with a composite <code className="mx-1 rounded-sm bg-paper-200 px-1">aria-label</code>{" "}
        (label, id, phase, confidence, timestamp, removal/override when applicable).
      </p>
      <ul className="space-y-3">
        <li className="flex flex-wrap items-center gap-2">
          <span className="w-28 shrink-0">Default</span>
          <ChipShell label="07:11 digest" />
        </li>
        <li className="flex flex-wrap items-center gap-2">
          <span className="w-28 shrink-0">Compact</span>
          <ChipShell label="07:11 digest" variant="compact" />
        </li>
        <li className="flex flex-wrap items-center gap-2">
          <span className="w-28 shrink-0">Overridden</span>
          <ChipShell label="Prior estimate" visualState="overridden" />
        </li>
        <li className="flex flex-wrap items-center gap-2">
          <span className="w-28 shrink-0">Tombstoned</span>
          <ChipShell label="Gone line item" visualState="tombstoned" />
        </li>
        <li className="flex flex-wrap items-center gap-2">
          <span className="w-28 shrink-0">Expand inert</span>
          <ChipShell label="Locked" disableExpand />
        </li>
      </ul>
    </div>
  ),
};
