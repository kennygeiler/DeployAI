"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Briefcase, Settings } from "lucide-react";

import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }> };

/**
 * MVP nav: Engagements (portfolio + per-engagement matrix + insights)
 * and Settings (tenant LLM config — Sprint 1). The pre-pivot BMAD
 * surfaces (`/digest`, `/in-meeting`, `/phase-tracking`, `/evening`,
 * `/action-queue`, `/validation-queue`, `/overrides`, `/audit/personal`,
 * `/settings/integrations`) are being retired — see
 * `docs/product/deployai-source-of-truth-spec.md` §16.
 */
const primary: readonly NavItem[] = [
  { href: "/engagements", label: "Engagements", icon: Briefcase },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function StrategistNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Primary strategist"
      className="bg-paper-100 border-border flex w-[56px] shrink-0 flex-col border-r xl:w-[240px]"
    >
      <div className="border-border hidden h-14 items-center border-b px-3 xl:flex">
        <Link
          href="/engagements"
          className="text-ink-900 focus-visible:ring-ring truncate font-semibold focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
        >
          DeployAI
        </Link>
      </div>
      <div className="flex flex-1 flex-col gap-4 py-3">
        <ul className="flex flex-col gap-0.5">
          {primary.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                className={cn(
                  "focus-visible:ring-ring flex items-center gap-3 py-2 pr-2 pl-2 xl:pl-3",
                  "hover:bg-paper-200 rounded-md",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
                  pathname === item.href || pathname?.startsWith(`${item.href}/`)
                    ? "bg-paper-200 text-ink-950 font-medium"
                    : "text-ink-700",
                )}
                title={item.label}
              >
                <item.icon className="text-ink-600 size-5 shrink-0" aria-hidden />
                <span className="hidden min-w-0 flex-1 truncate text-sm xl:inline">
                  {item.label}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
