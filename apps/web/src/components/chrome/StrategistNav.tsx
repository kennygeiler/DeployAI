"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  CheckSquare,
  FileWarning,
  ListChecks,
  ListTodo,
  Settings,
  Sun,
  UserRound,
  Video,
} from "lucide-react";

import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }> };

const primary: readonly NavItem[] = [
  { href: "/digest", label: "Morning digest", icon: Sun },
  { href: "/in-meeting", label: "In-meeting alert", icon: Video },
  { href: "/phase-tracking", label: "Phase & tasks", icon: ListChecks },
  { href: "/evening", label: "Evening synthesis", icon: BookOpen },
  { href: "/action-queue", label: "Action queue", icon: ListTodo },
  { href: "/validation-queue", label: "Validation queue", icon: CheckSquare },
];

const secondary: readonly NavItem[] = [
  { href: "/settings/integrations", label: "Integrations", icon: Settings },
  { href: "/overrides", label: "Override history", icon: FileWarning },
  { href: "/audit/personal", label: "Personal audit", icon: UserRound },
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
          href="/"
          className="text-ink-900 focus-visible:ring-ring truncate font-semibold focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
        >
          DeployAI
        </Link>
      </div>
      <div className="flex flex-1 flex-col gap-4 py-3">
        <div>
          <p className="text-ink-500 hidden px-3 pb-1 text-xs font-medium tracking-wide uppercase xl:block">
            Primary
          </p>
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
        <div>
          <p className="text-ink-500 hidden px-3 pb-1 text-xs font-medium tracking-wide uppercase xl:block">
            Secondary
          </p>
          <ul className="flex flex-col gap-0.5">
            {secondary.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    "focus-visible:ring-ring text-ink-600 flex items-center gap-3 py-2 pr-2 pl-2 opacity-80 xl:pl-3",
                    "hover:bg-paper-200 rounded-md",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
                    pathname === item.href ? "text-ink-900 bg-paper-200 font-medium" : null,
                  )}
                  title={item.label}
                >
                  <item.icon className="size-5 shrink-0" aria-hidden />
                  <span className="hidden min-w-0 flex-1 truncate text-sm xl:inline">
                    {item.label}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </nav>
  );
}
