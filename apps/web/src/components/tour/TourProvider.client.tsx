"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  TOUR_CAPTURE_PREFILL_EVENT,
  TOUR_COOKIE,
  TOUR_DISMISSED_KEY,
  TOUR_PREFILL_EVENT,
  TOUR_REPO_URL,
  TOUR_STEP_KEY,
  TOUR_STEPS,
  matchesRoutePattern,
  resolveTourRoutePattern,
  type TourStep,
} from "@/lib/tour/steps";

/**
 * Wave 3 K6 — the guided demo tour.
 *
 * Mounts in the strategist layout (so it survives navigation) and activates
 * only when the non-httpOnly `demo_tour=1` cookie is present (set by
 * /api/auth/demo) and the visitor hasn't skipped/finished it this session.
 *
 * Spotlight: four dimming rects around the target's bounding box — all
 * `pointer-events: none`, so the whole page (target included) stays
 * clickable and the tour never traps the visitor. When a step's target is
 * missing from the DOM (e.g. no citations rendered), the popover centers
 * itself and Next remains the escape hatch. Step index and dismissal live
 * in sessionStorage; positions are rAF-throttled on scroll/resize plus a
 * slow re-query interval so late-mounting targets get picked up.
 */

type Rect = { top: number; left: number; width: number; height: number };

function readCookie(name: string): string | null {
  const found = document.cookie
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${name}=`));
  return found ? decodeURIComponent(found.slice(name.length + 1)) : null;
}

function sameRect(a: Rect | null, b: Rect | null): boolean {
  if (a === null || b === null) return a === b;
  return a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), Math.max(lo, hi));
}

const SPOT_PAD = 6;
const POP_GAP = 12;
const POP_MARGIN = 12;

export function TourProvider() {
  const pathname = usePathname();
  const [active, setActive] = React.useState(false);
  const [stepIndex, setStepIndex] = React.useState(0);
  const [rect, setRect] = React.useState<Rect | null>(null);
  const [popPos, setPopPos] = React.useState<{ top: number; left: number } | null>(null);
  const popRef = React.useRef<HTMLDivElement>(null);
  const scrolledStepRef = React.useRef<number>(-1);

  const step: TourStep | undefined = TOUR_STEPS[stepIndex];
  const lastIndex = TOUR_STEPS.length - 1;

  // Mount gate — cookie present, not dismissed this session. Client-only so
  // the server render (which can't see sessionStorage) stays empty.
  React.useEffect(() => {
    if (readCookie(TOUR_COOKIE) !== "1") return;
    if (window.sessionStorage.getItem(TOUR_DISMISSED_KEY) === "1") return;
    const saved = Number.parseInt(window.sessionStorage.getItem(TOUR_STEP_KEY) ?? "0", 10);
    // Deferred a tick (same trick as EngagementBrief's detailEnabled) so the
    // activation setState never runs synchronously inside the effect body.
    const t = window.setTimeout(() => {
      setStepIndex(Number.isInteger(saved) ? clamp(saved, 0, TOUR_STEPS.length - 1) : 0);
      setActive(true);
    }, 0);
    return () => window.clearTimeout(t);
  }, []);

  const goTo = React.useCallback((index: number) => {
    const next = clamp(index, 0, TOUR_STEPS.length - 1);
    window.sessionStorage.setItem(TOUR_STEP_KEY, String(next));
    setStepIndex(next);
  }, []);

  const dismiss = React.useCallback(() => {
    window.sessionStorage.setItem(TOUR_DISMISSED_KEY, "1");
    setActive(false);
  }, []);

  const advance = React.useCallback(() => {
    setStepIndex((i) => {
      if (i >= TOUR_STEPS.length - 1) {
        window.sessionStorage.setItem(TOUR_DISMISSED_KEY, "1");
        setActive(false);
        return i;
      }
      window.sessionStorage.setItem(TOUR_STEP_KEY, String(i + 1));
      return i + 1;
    });
  }, []);

  const back = React.useCallback(() => {
    setStepIndex((i) => {
      const prev = Math.max(0, i - 1);
      window.sessionStorage.setItem(TOUR_STEP_KEY, String(prev));
      return prev;
    });
  }, []);

  const restart = React.useCallback(() => {
    window.sessionStorage.removeItem(TOUR_DISMISSED_KEY);
    goTo(0);
    setActive(true);
  }, [goTo]);

  // --- Target measurement: rAF-throttled on scroll/resize + a slow
  // re-query interval so targets that mount late (citations, tab panels)
  // get spotlighted without a navigation.
  React.useEffect(() => {
    if (!active || !step) return;
    let raf = 0;
    let queued = false;
    const measure = () => {
      queued = false;
      const el = step.target
        ? document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`)
        : null;
      if (el && scrolledStepRef.current !== stepIndex) {
        scrolledStepRef.current = stepIndex;
        // Optional call: jsdom has no scrollIntoView.
        el.scrollIntoView?.({ block: "center", behavior: "smooth" });
      }
      const r = el ? el.getBoundingClientRect() : null;
      const next: Rect | null = r
        ? {
            top: Math.round(r.top),
            left: Math.round(r.left),
            width: Math.round(r.width),
            height: Math.round(r.height),
          }
        : null;
      setRect((prev) => (sameRect(prev, next) ? prev : next));
    };
    const schedule = () => {
      if (queued) return;
      queued = true;
      raf = window.requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", schedule, true);
    window.addEventListener("resize", schedule);
    const interval = window.setInterval(schedule, 500);
    return () => {
      window.removeEventListener("scroll", schedule, true);
      window.removeEventListener("resize", schedule);
      window.clearInterval(interval);
      window.cancelAnimationFrame(raf);
    };
  }, [active, step, stepIndex, pathname]);

  // --- Advance triggers.
  React.useEffect(() => {
    if (!active || !step) return;
    const adv = step.advanceOn;
    if (adv.type === "event") {
      const onEvent = () => advance();
      window.addEventListener(adv.name, onEvent);
      return () => window.removeEventListener(adv.name, onEvent);
    }
    if (adv.type === "click-target" && step.target) {
      const selector = `[data-tour="${step.target}"]`;
      const onClick = (e: MouseEvent) => {
        const target = e.target;
        if (target instanceof Element && target.closest(selector)) advance();
      };
      document.addEventListener("click", onClick, true);
      return () => document.removeEventListener("click", onClick, true);
    }
    return undefined;
  }, [active, step, advance]);

  React.useEffect(() => {
    if (!active || !step || step.advanceOn.type !== "route" || !pathname) return;
    // Per-guest sandbox: the Acme-path sentinel resolves to THIS visitor's
    // sandbox engagement (demo_engagement cookie), falling back to the
    // stable Acme id for presenter/local flows without a sandbox.
    const pattern = resolveTourRoutePattern(step.advanceOn.pattern, document.cookie);
    if (!matchesRoutePattern(pathname, pattern)) return;
    const t = window.setTimeout(advance, 0);
    return () => window.clearTimeout(t);
  }, [active, step, pathname, advance]);

  // --- Popover placement: below the target when it fits, else above;
  // clamped to the viewport. No target → centered.
  React.useLayoutEffect(() => {
    if (!active) return;
    const el = popRef.current;
    if (!el) return;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    if (!rect) {
      setPopPos({
        top: Math.max(POP_MARGIN, (vh - h) / 2),
        left: Math.max(POP_MARGIN, (vw - w) / 2),
      });
      return;
    }
    let top = rect.top + rect.height + SPOT_PAD + POP_GAP;
    if (top + h > vh - POP_MARGIN) top = rect.top - SPOT_PAD - POP_GAP - h;
    top = clamp(top, POP_MARGIN, vh - h - POP_MARGIN);
    const left = clamp(rect.left, POP_MARGIN, vw - w - POP_MARGIN);
    setPopPos({ top, left });
  }, [active, rect, stepIndex]);

  // --- Focus + keyboard. Focus moves to the popover on each step; Esc
  // skips from anywhere, arrows navigate while the popover has focus.
  React.useEffect(() => {
    if (!active) return;
    popRef.current?.focus();
  }, [active, stepIndex]);

  React.useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        dismiss();
        return;
      }
      // Arrows navigate only while focus is inside the popover, so page-level
      // arrow-key interactions (scrolling, inputs) are left alone.
      const pop = popRef.current;
      if (!pop || !(e.target instanceof Node) || !pop.contains(e.target)) return;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        advance();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        back();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, dismiss, advance, back]);

  const prefill = React.useCallback(() => {
    if (!step?.prefill) return;
    window.dispatchEvent(
      new CustomEvent(TOUR_PREFILL_EVENT, { detail: { question: step.prefill } }),
    );
  }, [step]);

  // K7 slip act — fetch the step's artifact and hand it to CaptureIngest via
  // the capture-prefill event. The visitor still presses Capture themselves;
  // the tour never fakes a click.
  const [artifactLoading, setArtifactLoading] = React.useState(false);
  const capturePrefill = React.useCallback(async () => {
    const cp = step?.capturePrefill;
    if (!cp) return;
    setArtifactLoading(true);
    try {
      const res = await fetch(cp.url);
      if (!res.ok) return;
      const text = await res.text();
      window.dispatchEvent(
        new CustomEvent(TOUR_CAPTURE_PREFILL_EVENT, { detail: { text, source: cp.source } }),
      );
    } catch {
      // Network hiccup — the visitor can paste manually; the popover stays up.
    } finally {
      setArtifactLoading(false);
    }
  }, [step]);

  if (!active || !step) return null;

  const spot: Rect | null = rect
    ? {
        top: rect.top - SPOT_PAD,
        left: rect.left - SPOT_PAD,
        width: rect.width + SPOT_PAD * 2,
        height: rect.height + SPOT_PAD * 2,
      }
    : null;
  const isFinale = stepIndex === lastIndex;

  return (
    <div data-testid="demo-tour">
      {/* Spotlight — four dimming rects around the target (all
          pointer-events-none: purely visual, the page stays interactive). */}
      {spot ? (
        <div aria-hidden="true" data-testid="demo-tour-spotlight">
          <div
            className="pointer-events-none fixed inset-x-0 top-0 z-[60] bg-black/40"
            style={{ height: Math.max(0, spot.top) }}
          />
          <div
            className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] bg-black/40"
            style={{ top: spot.top + spot.height }}
          />
          <div
            className="pointer-events-none fixed left-0 z-[60] bg-black/40"
            style={{ top: spot.top, height: spot.height, width: Math.max(0, spot.left) }}
          />
          <div
            className="pointer-events-none fixed right-0 z-[60] bg-black/40"
            style={{
              top: spot.top,
              height: spot.height,
              left: spot.left + spot.width,
            }}
          />
          <div
            className="pointer-events-none fixed z-[60] rounded-card ring-2 ring-accent-ink"
            style={{ top: spot.top, left: spot.left, width: spot.width, height: spot.height }}
          />
        </div>
      ) : (
        <div
          aria-hidden="true"
          data-testid="demo-tour-dim"
          className="pointer-events-none fixed inset-0 z-[60] bg-black/40"
        />
      )}

      {/* Popover — hairline surface card. */}
      <div
        ref={popRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Demo tour step ${stepIndex + 1} of ${TOUR_STEPS.length}: ${step.title}`}
        tabIndex={-1}
        data-testid="demo-tour-popover"
        data-tour-step={step.id}
        className="fixed z-[70] w-[22rem] max-w-[calc(100vw-1.5rem)] rounded-card border border-line bg-surface p-4 shadow-overlay outline-none"
        style={popPos ? { top: popPos.top, left: popPos.left } : { top: "40%", left: "50%" }}
      >
        <p className="font-mono text-[10px] tracking-wide text-ink-500 uppercase">
          Guided tour · {stepIndex + 1}/{TOUR_STEPS.length}
        </p>
        <div aria-live="polite">
          <h2 className="mt-1 text-sm font-semibold text-ink">{step.title}</h2>
          <p className="mt-1.5 text-xs leading-relaxed text-ink-600">{step.body}</p>
          <p className="mt-2 rounded-control bg-accent-tint px-2.5 py-1.5 text-xs font-medium text-accent-ink">
            {step.action}
          </p>
        </div>

        {step.prefill ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={prefill}
            data-testid="demo-tour-prefill"
            className="mt-2 h-7 px-2.5 text-xs"
          >
            Use this question
          </Button>
        ) : null}

        {step.capturePrefill ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void capturePrefill()}
            disabled={artifactLoading}
            data-testid="demo-tour-capture-prefill"
            className="mt-2 h-7 px-2.5 text-xs"
          >
            {artifactLoading ? "Loading…" : step.capturePrefill.label}
          </Button>
        ) : null}

        {step.download ? (
          <p className="mt-2 text-xs">
            <a
              href={step.download.href}
              download
              data-testid="demo-tour-download"
              className="font-medium text-accent-ink underline-offset-2 hover:underline"
            >
              {step.download.label}
            </a>
          </p>
        ) : null}

        {isFinale ? (
          <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
            <Link
              href="/overview"
              className="font-medium text-ink underline-offset-2 hover:underline"
            >
              Product overview
            </Link>
            <a
              href={TOUR_REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-ink underline-offset-2 hover:underline"
            >
              GitHub repo
            </a>
          </p>
        ) : null}

        <div className="mt-3 flex items-center justify-between gap-2">
          <ul className="flex items-center gap-1" aria-label="Tour progress">
            {TOUR_STEPS.map((s, i) => (
              <li
                key={s.id}
                aria-current={i === stepIndex ? "step" : undefined}
                className={
                  i === stepIndex
                    ? "size-1.5 rounded-full bg-accent-ink"
                    : "size-1.5 rounded-full bg-line-strong"
                }
              />
            ))}
          </ul>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={dismiss}
              data-testid="demo-tour-skip"
              className="h-7 px-2 text-xs text-ink-600"
            >
              Skip
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={back}
              disabled={stepIndex === 0}
              data-testid="demo-tour-back"
              className="h-7 px-2 text-xs"
            >
              Back
            </Button>
            {isFinale ? (
              <>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={restart}
                  data-testid="demo-tour-restart"
                  className="h-7 px-2 text-xs"
                >
                  Restart
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={advance}
                  data-testid="demo-tour-next"
                  className="h-7 px-2.5 text-xs"
                >
                  Done
                </Button>
              </>
            ) : (
              <Button
                type="button"
                size="sm"
                onClick={advance}
                data-testid="demo-tour-next"
                className="h-7 px-2.5 text-xs"
              >
                Next
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
