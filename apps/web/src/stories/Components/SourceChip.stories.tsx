import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { SourceChip, SourcesRow, type SourceChipSource } from "@/components/ui/source-chip";

/**
 * Components / SourceChip — Beautiful UI component 03's inline sources.
 * Numbered chips sit inline with streamed answer text; hover/focus opens a
 * popover with title, origin, and snippet. `SourcesRow` is the summary strip
 * under the answer.
 */
const meta = {
  title: "Components/SourceChip",
  component: SourceChip,
  tags: ["autodocs"],
} satisfies Meta<typeof SourceChip>;

export default meta;
type Story = StoryObj<typeof meta>;

const sources: SourceChipSource[] = [
  {
    index: 1,
    title: "Deployment matrix — Q3 snapshot",
    origin: "matrix/rev-42",
    snippet: "Coverage for the northern region increased 12% quarter over quarter.",
  },
  {
    index: 2,
    title: "Stakeholder interview: Ops director",
    origin: "interviews/2026-05-02",
    href: "https://example.com/interviews/2026-05-02",
  },
  { index: 3, title: "Engagement ledger entry 118", origin: "ledger/118" },
];

export const Inline: Story = {
  args: { source: sources[0]! },
  render: (args) => (
    <p className="max-w-md text-sm leading-relaxed text-ink">
      Coverage in the northern region is up 12% quarter over quarter <SourceChip {...args} />,
      driven mostly by the two new field teams <SourceChip source={sources[1]!} />.
    </p>
  ),
};

export const Row: Story = {
  args: { source: sources[0]! },
  render: () => <SourcesRow sources={sources} />,
};
