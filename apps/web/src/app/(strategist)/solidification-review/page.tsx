import Link from "next/link";

export default function SolidificationReviewPage() {
  return (
    <div className="max-w-2xl space-y-4">
      <h1 className="text-display text-ink-950 font-semibold tracking-tight">
        Solidification review
      </h1>
      <p className="text-body text-ink-600">
        Class B pattern promotion (Epic 9). Evening synthesis already links here; the queue UI
        follows when validation surfaces ship.
      </p>
      <Link
        href="/evening"
        className="text-evidence-800 text-sm font-medium underline-offset-2 hover:underline"
      >
        Back to Evening synthesis
      </Link>
    </div>
  );
}
