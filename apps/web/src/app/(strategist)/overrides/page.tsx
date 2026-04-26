import Link from "next/link";

export default function OverrideHistoryPage() {
  return (
    <div className="max-w-2xl space-y-4">
      <h1 className="text-display text-ink-950 font-semibold tracking-tight">Override history</h1>
      <p className="text-body text-ink-600">
        OverrideComposer and audit trail are Epic 10. Nav target only for chrome completeness.
      </p>
      <Link
        href="/digest"
        className="text-evidence-800 text-sm font-medium underline-offset-2 hover:underline"
      >
        Back to Morning digest
      </Link>
    </div>
  );
}
