import Link from "next/link";

export default function ValidationQueuePage() {
  return (
    <div className="max-w-2xl space-y-4">
      <h1 className="text-display text-ink-950 font-semibold tracking-tight">Validation queue</h1>
      <p className="text-body text-ink-600">
        User Validation Queue and promote/demote actions land in Epic 9. This page exists so left
        nav and the command palette route resolve without 404.
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
