"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Briefcase, Cable, Gauge, Inbox, MessageCircle, Search, Settings } from "lucide-react";

import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }> };

/**
 * MVP nav: Engagements (portfolio + per-engagement matrix + insights),
 * the Review inbox (pilot-refresh E1 — unified HITL queue with an
 * open-item badge), and Settings (tenant LLM config — Sprint 1). The
 * pre-pivot BMAD surfaces (`/digest`, `/in-meeting`, `/phase-tracking`,
 * `/evening`, `/action-queue`, `/validation-queue`, `/overrides`,
 * `/audit/personal`, `/settings/integrations`) are being retired — see
 * `docs/product/deployai-source-of-truth-spec.md` §16.
 */
const primary: readonly NavItem[] = [
  { href: "/engagements", label: "Engagements", icon: Briefcase },
  // Wave 2.5 U10 — global Kenny: engagement-scoped Q&A from anywhere.
  { href: "/ask", label: "Ask", icon: MessageCircle },
  { href: "/review", label: "Review inbox", icon: Inbox },
  { href: "/search", label: "Search", icon: Search },
  { href: "/settings", label: "Settings", icon: Settings },
  // v2 Phase 5 Wave 3I — outbound MCP audit. The "Admin" surface grew
  // a second tab in Phase 6 Wave C (the Agent Kenny telemetry
  // dashboard). Both surfaces are tenant-scoped + read-only; the labels
  // keep the verbs ("activity" / "dashboard") so a strategist scanning
  // the sidebar knows which page tells them what. Lucide's ``Cable``
  // icon reads as "external connector"; ``Gauge`` as "health readout".
  { href: "/admin/agent-kenny-mcp-activity", label: "Admin · MCP activity", icon: Cable },
  { href: "/admin/agent-kenny-dashboard", label: "Admin · Agent Kenny dashboard", icon: Gauge },
];

function useOpenReviewCount(): number {
  const [count, setCount] = React.useState(0);
  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await fetch("/api/bff/review/badge", { cache: "no-store" });
        if (!r.ok || cancelled) {
          return;
        }
        const body = (await r.json()) as { counts?: { open?: number } };
        if (!cancelled && typeof body.counts?.open === "number") {
          setCount(body.counts.open);
        }
      } catch {
        // Badge is best-effort chrome — a failed fetch just shows no count.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  return count;
}

export function StrategistNav() {
  const pathname = usePathname();
  const openReviewCount = useOpenReviewCount();
  return (
    <nav
      aria-label="Primary strategist"
      className="flex w-[56px] shrink-0 flex-col border-r border-line bg-canvas xl:w-[240px]"
    >
      <div className="hidden h-14 items-center border-b border-line px-3 xl:flex">
        <Link
          href="/engagements"
          className="truncate font-semibold text-ink focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          DeployAI
        </Link>
      </div>
      {/* Sidebar Nav — Beautiful UI component 14: active item is a raised
          surface pill; inactive items are quiet ink-2 rows. */}
      <div className="flex flex-1 flex-col gap-4 px-1.5 py-3 xl:px-2">
        <ul className="flex flex-col gap-0.5">
          {primary.map((item) => {
            const active = pathname === item.href || pathname?.startsWith(`${item.href}/`);
            const showBadge = item.href === "/review" && openReviewCount > 0;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-control py-2 pr-2 pl-2 xl:pl-2.5",
                    "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none",
                    active
                      ? "bg-surface font-medium text-ink shadow-btn"
                      : "text-ink-600 transition-colors hover:bg-hover hover:text-ink",
                  )}
                  title={item.label}
                >
                  <item.icon
                    className={cn("size-5 shrink-0", active ? "text-ink" : "text-ink-600")}
                    aria-hidden
                  />
                  <span className="hidden min-w-0 flex-1 truncate text-sm xl:inline">
                    {item.label}
                  </span>
                  {showBadge ? (
                    <span
                      aria-label={`${openReviewCount} open review item(s)`}
                      className="hidden rounded-full bg-accent-tint px-1.5 py-0.5 font-mono text-[10px] font-semibold text-accent-ink shadow-hairline xl:inline"
                    >
                      {openReviewCount}
                    </span>
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}
