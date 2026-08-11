"use client";

import Link from "next/link";
import * as React from "react";

import { Button } from "@/components/ui/button";

/**
 * W1 — route-group error boundary for every strategist surface. Renders a
 * calm Beautiful UI card instead of the Next.js default crash overlay and
 * offers a reset. Digest is shown (when present) so support tickets can be
 * correlated with server logs without exposing stack traces.
 */
export default function StrategistError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  React.useEffect(() => {
    // Surface in the console for local debugging; production consoles stay
    // quiet unless someone is actively looking.
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto flex min-h-[50vh] max-w-md items-center justify-center px-4">
      <div className="w-full rounded-card bg-surface p-6 text-center shadow-card">
        <p className="text-sm font-semibold text-ink">Something went wrong</p>
        <p className="mt-2 text-sm text-ink-600">
          This surface hit an unexpected error. Your data is safe — try again, or head back to the
          portfolio.
        </p>
        {error.digest ? (
          <p className="mt-2 font-mono text-[11px] text-ink-400">ref {error.digest}</p>
        ) : null}
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button type="button" size="sm" onClick={() => reset()}>
            Try again
          </Button>
          <Button size="sm" variant="outline" asChild>
            <Link href="/engagements">Back to engagements</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
