import type { Metadata } from "next";

import { EventSearch } from "@/components/search/EventSearch.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Search",
  description: "Substring search across every canonical event in the tenant.",
};

export default async function SearchPage() {
  await requireCanonicalRead();
  return (
    <div className="max-w-5xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Search</h1>
        <p className="text-ink-600 mt-1 text-sm">
          Find any email, meeting note, or field note ever ingested into your tenant.
        </p>
      </header>
      <EventSearch />
    </div>
  );
}
