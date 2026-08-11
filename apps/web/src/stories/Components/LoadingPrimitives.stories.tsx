import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { PixelLoader, Shimmer, ShimmerLines } from "@/components/ui/shimmer";

/**
 * Components / LoadingPrimitives — Beautiful UI component 01. `Shimmer` and
 * `ShimmerLines` are the skeleton blocks used by route `loading.tsx` files;
 * `PixelLoader` is the pixel-grid loader with a live elapsed-time counter
 * used while agent work is in flight.
 */
const meta = {
  title: "Components/LoadingPrimitives",
  component: PixelLoader,
  tags: ["autodocs"],
} satisfies Meta<typeof PixelLoader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const PixelGridLoader: Story = {
  args: { label: "Churning" },
};

export const WithoutElapsedTime: Story = {
  args: { label: "Reading briefs", showElapsed: false },
};

export const ShimmerBlock: Story = {
  render: () => (
    <div className="max-w-md space-y-4">
      <Shimmer className="h-24 rounded-card" />
      <ShimmerLines lines={3} />
    </div>
  ),
};

export const SkeletonCard: Story = {
  render: () => (
    <div className="max-w-md rounded-card bg-surface p-4 shadow-card">
      <div className="flex items-center gap-3">
        <Shimmer className="size-8 rounded-full" />
        <Shimmer className="h-3.5 w-40" />
      </div>
      <ShimmerLines className="mt-4" lines={4} />
    </div>
  ),
};
