import { PixelLoader, Shimmer, ShimmerLines } from "@/components/ui/shimmer";

/**
 * W1 — engagement-detail loading skeleton: header block, activity strip,
 * and two card wells matching the detail layout's rhythm.
 */
export default function EngagementDetailLoading() {
  return (
    <div className="max-w-5xl space-y-6" aria-busy="true">
      <PixelLoader label="Loading engagement" />
      <div className="space-y-2">
        <Shimmer className="h-7 w-72 rounded-md" />
        <Shimmer className="h-4 w-96 max-w-full" />
      </div>
      <div className="flex gap-2">
        <Shimmer className="h-8 w-28 rounded-full" />
        <Shimmer className="h-8 w-28 rounded-full" />
        <Shimmer className="h-8 w-28 rounded-full" />
      </div>
      <div className="rounded-card bg-surface p-4 shadow-card">
        <Shimmer className="mb-3 h-4 w-32" />
        <ShimmerLines lines={4} />
      </div>
      <div className="rounded-card bg-surface p-4 shadow-card">
        <Shimmer className="mb-3 h-4 w-44" />
        <ShimmerLines lines={6} />
      </div>
    </div>
  );
}
