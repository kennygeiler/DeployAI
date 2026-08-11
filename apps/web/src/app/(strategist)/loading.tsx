import { PixelLoader, Shimmer, ShimmerLines } from "@/components/ui/shimmer";

/**
 * W1 — route-group loading state. Shimmer skeleton (Beautiful UI
 * component 01) that mirrors the typical strategist page: heading, a
 * card-shaped well, and a records-table block.
 */
export default function StrategistLoading() {
  return (
    <div className="max-w-5xl space-y-6" aria-busy="true">
      <PixelLoader label="Loading" />
      <div className="space-y-2">
        <Shimmer className="h-7 w-56 rounded-md" />
        <Shimmer className="h-4 w-80" />
      </div>
      <div className="rounded-card bg-surface p-4 shadow-card">
        <ShimmerLines lines={3} />
      </div>
      <div className="rounded-card bg-surface p-4 shadow-card">
        <Shimmer className="mb-3 h-4 w-40" />
        <ShimmerLines lines={5} />
      </div>
    </div>
  );
}
