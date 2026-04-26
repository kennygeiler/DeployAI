"use client";

import { DigestEvidenceCard } from "@/components/epic8/DigestEvidenceCard.client";
import { StrategistBreadcrumb } from "@/components/chrome/StrategistBreadcrumb";
import type { DigestTopItem } from "@/lib/epic8/mock-digest";

export function EvidenceNodePageClient({ item }: { item: DigestTopItem }) {
  const short = item.id.length > 12 ? `${item.id.slice(0, 8)}…` : item.id;
  return (
    <div className="flex flex-col gap-6">
      <StrategistBreadcrumb
        data-testid="evidence-breadcrumb"
        items={[
          { href: "/digest", label: "Morning digest" },
          { label: "Evidence" },
          { label: short, current: true },
        ]}
      />
      <div>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">Evidence node</h1>
        <p className="text-body text-ink-600 mt-1 max-w-2xl">
          Canonical view for node <code className="font-mono text-xs">{item.id}</code> (Story
          8.4). Expand-inline defaults open here; production resolves from canonical memory.
        </p>
      </div>
      <DigestEvidenceCard item={item} headingLevel="h2" defaultExpanded />
    </div>
  );
}
