"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

type Crumb = { href?: string; label: string; current?: boolean };

export function StrategistBreadcrumb({
  items,
  className,
  "data-testid": testId,
}: {
  items: readonly Crumb[];
  className?: string;
  "data-testid"?: string;
}) {
  return (
    <nav
      aria-label="Breadcrumb"
      data-testid={testId}
      className={cn("text-ink-600 text-sm", className)}
    >
      <ol className="flex flex-wrap items-center gap-1">
        {items.map((c, i) => (
          <li key={c.label} className="flex min-w-0 items-center gap-1">
            {i > 0 ? <ChevronRight className="text-ink-400 size-3.5 shrink-0" aria-hidden /> : null}
            {c.href && !c.current ? (
              <Link
                href={c.href}
                className="text-evidence-800 hover:text-evidence-950 truncate underline-offset-2 hover:underline"
              >
                {c.label}
              </Link>
            ) : (
              <span
                className={cn("truncate", c.current ? "text-ink-900 font-medium" : null)}
                aria-current={c.current ? "page" : undefined}
              >
                {c.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
