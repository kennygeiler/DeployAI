import Link from "next/link";

export default function PersonalAuditPage() {
  return (
    <div className="max-w-2xl space-y-4">
      <h1 className="text-display text-ink-950 font-semibold tracking-tight">Personal audit</h1>
      <p className="text-body text-ink-600">
        Private annotations and personal audit (Epic 10). Placeholder route for strategist chrome.
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
