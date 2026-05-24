import type { Metadata } from "next";

import { AuditLogList } from "@/components/settings/AuditLogList.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Audit log",
  description: "Recent strategist activity events for the current tenant.",
};

export default async function AuditLogPage() {
  await requireCanonicalRead();
  return (
    <div className="max-w-5xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Audit log</h1>
        <p className="text-ink-600 mt-1 text-sm">
          Append-only record of strategist actions taken on this tenant. Filter by actor or event
          kind; load older events with the button below.
        </p>
      </header>
      <AuditLogList />
    </div>
  );
}
