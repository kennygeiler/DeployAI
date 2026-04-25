"use client";

import * as React from "react";
import { Bell, MessageSquare, PanelBottomClose } from "lucide-react";

import { cn } from "./lib/utils";

const W = 360;
const H = 240;
const PEEK = 40;
const MARGIN = 24;
const NUDGE = 8;

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function defaultPosition() {
  if (typeof window === "undefined") {
    return { left: 48, top: 48 };
  }
  return {
    left: Math.max(MARGIN, window.innerWidth - W - MARGIN),
    top: Math.max(MARGIN, window.innerHeight - H - MARGIN),
  };
}

function clampToViewport(
  left: number,
  top: number,
  w: number,
  h: number,
): { left: number; top: number } {
  if (typeof window === "undefined") {
    return { left, top };
  }
  const maxL = window.innerWidth - w - MARGIN;
  const maxT = window.innerHeight - h - MARGIN;
  return {
    left: Math.min(Math.max(MARGIN, left), maxL),
    top: Math.min(Math.max(MARGIN, top), maxT),
  };
}

function readPosition(key: string): { left: number; top: number } | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return null;
    }
    const o = JSON.parse(raw) as { left?: number; top?: number };
    if (typeof o.left === "number" && typeof o.top === "number") {
      return { left: o.left, top: o.top };
    }
  } catch {
    /* ignore */
  }
  return null;
}

function writePosition(key: string, p: { left: number; top: number }) {
  try {
    window.localStorage.setItem(key, JSON.stringify(p));
  } catch {
    /* quota / private mode */
  }
}

export type InMeetingAlertState = "active" | "idle" | "degraded" | "collapsed" | "archived";

export type InMeetingAlertCardProps = {
  tenantId: string;
  meetingTitle: string;
  phaseLabel: string;
  freshnessLabel: string;
  /** Up to 3 `CitationChip` (or other) nodes; host limits count. */
  children?: React.ReactNode;
  state: InMeetingAlertState;
  /**
   * Defaults to `tenant:<tenantId>:alert:position` (JSON { left, top } for `position: fixed`).
   * Override for tests (pass e.g. a random key) to isolate storage.
   */
  positionStorageKey?: string;
  className?: string;
  /** "Not now" — dismiss to tray (host handles persistence). */
  onNotNow?: () => void;
};

/**
 * In-meeting floating alert (UX-DR9, FR36). `role="complementary"`, 360×240 expanded,
 * 40×40 peek, position persisted in `localStorage`, pointer drag on header, **Alt+Arrow** nudge
 * (UX-DR26 keyboard move), **Cmd+\\** / **Ctrl+\\** expands + focus-traps, **Esc** collapses
 * to peek without unmounting. When `state === "archived"`, returns `null` (surface shows from history).
 */
export function InMeetingAlertCard({
  tenantId,
  meetingTitle,
  phaseLabel,
  freshnessLabel,
  children,
  state: stateProp,
  positionStorageKey: positionStorageKeyProp,
  className: classNameProp,
  onNotNow,
}: InMeetingAlertCardProps) {
  const storageKey = positionStorageKeyProp ?? `tenant:${tenantId}:alert:position`;
  const cardRef = React.useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = React.useState(defaultPosition);
  const [peeking, setPeeking] = React.useState(() => stateProp === "collapsed");
  const [focusTrap, setFocusTrap] = React.useState(false);
  const drag = React.useRef<{
    active: boolean;
    dx: number;
    dy: number;
    w: number;
    h: number;
  } | null>(null);

  const hydrated = React.useRef(false);
  React.useLayoutEffect(() => {
    if (hydrated.current) {
      return;
    }
    hydrated.current = true;
    const s = readPosition(storageKey);
    if (s) {
      setPos(s);
    } else {
      setPos(defaultPosition);
    }
  }, [storageKey]);

  React.useEffect(() => {
    if (stateProp === "collapsed") {
      setPeeking(true);
    }
  }, [stateProp]);

  const expanded = !peeking;
  const w = expanded ? W : PEEK;
  const h = expanded ? H : PEEK;
  const effectivePos = React.useMemo(
    () => clampToViewport(pos.left, pos.top, w, h),
    [pos, w, h],
  );

  // Focus trap when summoned via keyboard shortcut
  React.useEffect(() => {
    if (!focusTrap || !expanded) {
      return;
    }
    const root = cardRef.current;
    if (!root) {
      return;
    }
    const nodes = () => Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));
    const list = nodes();
    const first = list[0] ?? root;
    first.focus({ preventScroll: true });

    const onDocKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || !root) {
        return;
      }
      const focusables = nodes();
      if (focusables.length === 0) {
        return;
      }
      const i = focusables.indexOf(document.activeElement as HTMLElement);
      if (e.shiftKey) {
        if (i <= 0) {
          e.preventDefault();
          focusables[focusables.length - 1]?.focus();
        }
      } else if (i === -1 || i === focusables.length - 1) {
        e.preventDefault();
        focusables[0]?.focus();
      }
    };
    document.addEventListener("keydown", onDocKey, true);
    return () => {
      document.removeEventListener("keydown", onDocKey, true);
    };
  }, [focusTrap, expanded]);

  // Cmd+\ / Ctrl+\ to expand + trap; Esc to collapse (peek)
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const isSummon =
        (e.key === "\\" || e.code === "Backslash") && (e.metaKey || e.ctrlKey);
      if (isSummon) {
        e.preventDefault();
        setPeeking(false);
        setFocusTrap(true);
        return;
      }
      if (e.key === "Escape" && !peeking) {
        const t = e.target;
        if (t instanceof Element && t.closest("[data-citation-chip]")) {
          return;
        }
        e.preventDefault();
        setPeeking(true);
        setFocusTrap(false);
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
    };
  }, [peeking]);

  // Alt + Arrow: move when focus is inside the card (UX-DR26 keyboard move)
  React.useEffect(() => {
    const onDoc = (e: KeyboardEvent) => {
      if (!e.altKey || !cardRef.current) {
        return;
      }
      const t = e.target;
      if (!(t instanceof Node) || !cardRef.current.contains(t)) {
        return;
      }
      const k = e.key;
      if (k !== "ArrowUp" && k !== "ArrowDown" && k !== "ArrowLeft" && k !== "ArrowRight") {
        return;
      }
      e.preventDefault();
      setPos((p) => {
        const n =
          k === "ArrowUp"
            ? { left: p.left, top: p.top - NUDGE }
            : k === "ArrowDown"
              ? { left: p.left, top: p.top + NUDGE }
              : k === "ArrowLeft"
                ? { left: p.left - NUDGE, top: p.top }
                : { left: p.left + NUDGE, top: p.top };
        const c = clampToViewport(n.left, n.top, w, h);
        writePosition(storageKey, c);
        return c;
      });
    };
    document.addEventListener("keydown", onDoc, true);
    return () => {
      document.removeEventListener("keydown", onDoc, true);
    };
  }, [storageKey, w, h]);

  const onPointerDownHeader = (e: React.PointerEvent) => {
    if (e.button !== 0) {
      return;
    }
    e.preventDefault();
    const el = cardRef.current;
    if (!el) {
      return;
    }
    const rect = el.getBoundingClientRect();
    drag.current = {
      active: true,
      dx: e.clientX - rect.left,
      dy: e.clientY - rect.top,
      w,
      h,
    };
    el.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current?.active) {
      return;
    }
    const d = drag.current;
    const left = e.clientX - d.dx;
    const top = e.clientY - d.dy;
    const c = clampToViewport(left, top, d.w, d.h);
    setPos(c);
  };

  const onPointerUp = (e: React.PointerEvent) => {
    if (!drag.current?.active) {
      return;
    }
    drag.current.active = false;
    if (cardRef.current?.hasPointerCapture(e.pointerId)) {
      cardRef.current.releasePointerCapture(e.pointerId);
    }
    setPos((p) => {
      const c = clampToViewport(p.left, p.top, w, h);
      writePosition(storageKey, c);
      return c;
    });
  };

  if (stateProp === "archived") {
    return null;
  }

  return (
    <div
      ref={cardRef}
      role="complementary"
      aria-label="In-meeting alert"
      className={cn("fixed z-50", classNameProp)}
      style={{
        left: effectivePos.left,
        top: effectivePos.top,
        width: w,
        minHeight: h,
        maxHeight: h,
      }}
    >
      {peeking ? (
        <button
          type="button"
          className="flex size-10 min-h-11 min-w-11 items-center justify-center rounded-lg border border-border bg-paper-100 text-ink-900 shadow-md hover:bg-paper-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          aria-label="Expand in-meeting alert"
          onClick={() => {
            setPeeking(false);
            setFocusTrap(true);
          }}
        >
          <Bell className="size-5" aria-hidden />
        </button>
      ) : (
        <div
          className={cn(
            "flex h-full w-full flex-col overflow-hidden rounded-lg border border-border bg-paper-100 text-ink-900 shadow-lg",
            stateProp === "idle" && "opacity-80",
            stateProp === "degraded" && "border-amber-600/50 ring-1 ring-amber-500/20",
          )}
        >
          <div
            role="presentation"
            className="flex cursor-grab touch-none select-none items-center justify-between border-b border-border bg-paper-200/80 px-3 py-2 active:cursor-grabbing"
            onPointerDown={onPointerDownHeader}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-ink-900">
                {meetingTitle}
              </p>
              <p className="truncate text-xs text-ink-600">
                {phaseLabel} — {freshnessLabel}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {stateProp === "degraded" ? (
                <span className="rounded border border-amber-600/40 bg-amber-50/90 px-1.5 py-0.5 text-[0.65rem] font-medium text-amber-950">
                  Degraded
                </span>
              ) : null}
            </div>
          </div>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
            <p className="text-xs text-ink-600">Retrieved for this meeting (max 3)</p>
            <div className="flex flex-col gap-2">{children}</div>
          </div>
          <div className="flex items-center justify-between border-t border-border bg-paper-200/50 px-2 py-1.5">
            <button
              type="button"
              className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs text-ink-700 hover:bg-paper-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
              onClick={() => onNotNow?.()}
            >
              <MessageSquare className="size-3.5" aria-hidden />
              Not now
            </button>
            <button
              type="button"
              className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs text-ink-700 hover:bg-paper-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
              onClick={() => {
                setPeeking(true);
                setFocusTrap(false);
              }}
            >
              <PanelBottomClose className="size-3.5" aria-hidden />
              Collapse
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
