import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";

import { CitationChip, InMeetingAlertCard, type InMeetingAlertState } from "@deployai/shared-ui";

const meta: Meta<typeof InMeetingAlertCard> = {
  title: "Components/InMeetingAlertCard",
  component: InMeetingAlertCard,
  tags: ["autodocs"],
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "In-meeting floating alert (UX-DR9). Cmd+Backslash or Ctrl+Backslash expands and focus-traps; Esc collapses to peek. Drag header to move; Alt+Arrow nudges when focus is inside.",
      },
    },
  },
  decorators: [(s) => <div className="bg-paper-200 relative min-h-[520px] w-full">{s()}</div>],
} satisfies Meta<typeof InMeetingAlertCard>;

export default meta;
type Story = StoryObj<typeof meta>;

const preview = {
  citationId: "c-node-1",
  retrievalPhase: "P4",
  confidence: "0.91",
  signedTimestamp: "2026-02-03T14:00:00Z",
};

function DemoChip({ label }: { label: string }) {
  const [ex, setEx] = useState(false);
  return (
    <CitationChip
      label={label}
      expanded={ex}
      onToggleExpand={() => {
        setEx((v) => !v);
      }}
      preview={preview}
      onViewEvidence={() => {}}
      onOverride={() => {}}
      onCopyLink={() => {}}
      onCiteInOverride={() => {}}
      variant="compact"
    />
  );
}

const chips = (
  <>
    <DemoChip label="Cable Sect 15" />
    <DemoChip label="GC commitment Feb 3" />
  </>
);

function CardStory({
  state,
  freshnessLabel = "synced 6s ago",
  storageKey,
}: {
  state: InMeetingAlertState;
  freshnessLabel?: string;
  storageKey: string;
}) {
  return (
    <InMeetingAlertCard
      tenantId="00000000-0000-4000-8000-000000000001"
      meetingTitle="Meeting with GC Nwankwo"
      phaseLabel="P5 — Pilot"
      freshnessLabel={freshnessLabel}
      state={state}
      positionStorageKey={storageKey}
    >
      {chips}
    </InMeetingAlertCard>
  );
}

export const Active: Story = {
  render: () => <CardStory state="active" storageKey="sb-in-meeting-active" />,
};

export const Idle: Story = {
  render: () => (
    <CardStory state="idle" freshnessLabel="synced 72s ago" storageKey="sb-in-meeting-idle" />
  ),
};

export const Degraded: Story = {
  render: () => (
    <CardStory
      state="degraded"
      freshnessLabel="stale (Cartographer behind)"
      storageKey="sb-in-meeting-degraded"
    />
  ),
};

export const CollapsedStart: Story = {
  render: () => <CardStory state="collapsed" storageKey="sb-in-meeting-collapsed" />,
};

export const ArchivedNote: Story = {
  render: function R() {
    return (
      <div className="p-4 text-sm text-ink-700">
        <p>
          When <code>state=&quot;archived&quot;</code>, the card unmounts — the host shows history
          elsewhere.
        </p>
        <p className="mt-2 text-ink-500">(No floating node — intentional.)</p>
      </div>
    );
  },
};
