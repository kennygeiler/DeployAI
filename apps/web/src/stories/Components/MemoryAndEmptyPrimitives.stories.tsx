import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { EmptyState, LoadingFromMemory, MemorySyncingGlyph } from "@deployai/shared-ui";

const meta: Meta = {
  title: "Components/Memory and empty (7-11)",
  tags: ["autodocs"],
  parameters: { layout: "padded" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const EmptyStateBasic: Story = {
  render: () => (
    <EmptyState
      title="No learnings in this phase yet"
      description="Connect a data source or wait for the next digest cycle."
      actionLabel="Open integrations"
      onAction={() => {}}
      docsUrl="https://docs.example.com"
      docsLabel="Read the integrations guide"
    />
  ),
};

export const LoadingFromMemoryWithChildren: Story = {
  render: () => (
    <LoadingFromMemory>
      <p className="text-sm text-ink-700">First result row can appear here progressively.</p>
    </LoadingFromMemory>
  ),
};

export const MemorySyncingGlyphRow: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <MemorySyncingGlyph state="syncing" label="Syncing memory…" />
      <MemorySyncingGlyph state="stale" label="Staleness above SLO" />
      <MemorySyncingGlyph state="unavailable" label="Memory unavailable" />
    </div>
  ),
};
