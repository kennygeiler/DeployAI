import Link from "next/link";

/**
 * W1 — app-level 404. Styled to the Beautiful UI system; server component
 * (no client JS needed).
 */
export default function NotFound() {
  return (
    <main
      id="main"
      tabIndex={-1}
      className="flex min-h-screen items-center justify-center bg-page px-4 outline-none"
    >
      <div className="w-full max-w-md rounded-card bg-surface p-6 text-center shadow-card">
        <p className="font-mono text-xs text-ink-400">404</p>
        <p className="mt-1 text-sm font-semibold text-ink">Page not found</p>
        <p className="mt-2 text-sm text-ink-600">
          The page you&apos;re looking for doesn&apos;t exist or may have moved.
        </p>
        <div className="mt-4">
          <Link
            href="/engagements"
            className="inline-flex h-8 items-center justify-center rounded-full bg-primary px-3 text-sm font-medium text-primary-foreground shadow-btn hover:bg-primary/90"
          >
            Back to engagements
          </Link>
        </div>
      </div>
    </main>
  );
}
