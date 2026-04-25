"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { ChevronDown } from "lucide-react";

import { cn } from "./lib/utils";
import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "./components/ui/popover";
import {
  type DeploymentPhaseDefinition,
  type DeploymentPhaseId,
  DEPLOYMENT_PHASES,
} from "./phases";

const triggerRoot = cva(
  "inline-flex h-8 min-w-0 max-w-full shrink-0 items-center justify-center gap-1.5 rounded-md border font-sans text-sm font-medium transition-colors " +
    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
    "data-[state=open]:ring-2 data-[state=open]:ring-ring/40",
  {
    variants: {
      tone: {
        default: "border-border bg-paper-100 text-ink-900 hover:bg-paper-200",
        "pending-transition":
          "border-amber-600/50 bg-amber-50/80 text-amber-950 ring-1 ring-amber-500/30 animate-pulse",
        locked: "border-border bg-muted/50 text-ink-600",
      },
    },
    defaultVariants: { tone: "default" },
  },
);

export type PhaseIndicatorVariant = NonNullable<VariantProps<typeof triggerRoot>["tone"]>;

export type PhaseIndicatorProps = {
  /** Current phase; must exist in `phases` (default: canonical seven). */
  currentPhaseId: DeploymentPhaseId;
  phases?: readonly DeploymentPhaseDefinition[];
  /** `default` — normal; `pending-transition` — proposed transition; `locked` — read-only (no popover). */
  variant?: PhaseIndicatorVariant;
  className?: string;
  id?: string;
};

/**
 * Top-left deployment phase chrome chip (UX-DR6). Click opens a popover stepper; phase
 * changes are announced with `aria-live="polite"`.
 */
export function PhaseIndicator({
  currentPhaseId,
  phases = DEPLOYMENT_PHASES,
  variant: variantProp = "default",
  className: classNameProp,
  id: idProp,
}: PhaseIndicatorProps) {
  const list = phases;
  if (list.length === 0) {
    return null;
  }
  const current = list.find((p) => p.id === currentPhaseId) ?? list[0]!;
  const i = Math.max(
    0,
    list.findIndex((p) => p.id === currentPhaseId),
  );
  const prior = i > 0 ? list[i - 1] : null;
  const next = i < list.length - 1 ? list[i + 1] : null;
  const baseId = idProp ?? React.useId();
  const liveId = `${baseId}-live`;

  const [liveText, setLiveText] = React.useState("");

  const prevPhase = React.useRef<DeploymentPhaseId | null>(null);
  React.useEffect(() => {
    if (prevPhase.current === null) {
      prevPhase.current = currentPhaseId;
      return;
    }
    if (prevPhase.current !== currentPhaseId) {
      setLiveText(`Now in ${current.label}.`);
      prevPhase.current = currentPhaseId;
    }
  }, [current.label, currentPhaseId]);

  const stepper = (
    <nav className="mt-2" aria-label="All deployment phases" data-testid="phase-stepper">
      <p className="text-xs text-ink-600">
        {prior ? (
          <>
            <span className="text-ink-600">Prior:</span> {prior.shortLabel} {prior.label}
          </>
        ) : null}
        {prior && next ? " · " : null}
        {next ? (
          <>
            <span className="text-ink-600">Next:</span> {next.shortLabel} {next.label}
          </>
        ) : null}
        {!prior && !next ? "Single phase" : null}
      </p>
      <ol className="mt-3 max-h-64 space-y-1 overflow-y-auto">
        {list.map((p) => {
          const isCurrent = p.id === currentPhaseId;
          const Icon = p.icon;
          return (
            <li
              key={p.id}
              aria-current={isCurrent ? "step" : undefined}
              className={cn(
                "flex min-h-9 items-center gap-2 rounded-sm border px-2 py-1.5 text-left text-sm",
                isCurrent
                  ? "border-evidence-700/40 bg-evidence-50 text-ink-900"
                  : "border-border/60 bg-card text-ink-700",
              )}
            >
              <Icon className="size-3.5 shrink-0 text-ink-500" aria-hidden />
              <span className="shrink-0 font-mono text-xs text-ink-500">{p.shortLabel}</span>
              <span className="min-w-0">{p.label}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );

  const triggerClasses = triggerRoot({ tone: variantProp });
  const label = (
    <span className="flex min-w-0 items-baseline gap-1.5">
      <span className="shrink-0 font-mono text-xs text-ink-500">{current.shortLabel}</span>
      <span className="min-w-0 truncate text-sm text-ink-900">{current.label}</span>
    </span>
  );

  const statusSlot = (
    <div id={liveId} className="sr-only" aria-live="polite" aria-atomic="true">
      {liveText}
    </div>
  );

  if (variantProp === "locked") {
    return (
      <div className={cn("relative min-w-0", classNameProp)}>
        {statusSlot}
        <div
          className={cn(
            "inline-flex h-8 w-[min(100%,18rem)] max-w-full cursor-not-allowed items-center gap-1 rounded-md border border-dashed border-border bg-muted/40 px-2.5 text-sm text-ink-600",
          )}
          title="Phase is read-only in this context"
          data-phase-indicator="locked"
        >
          {label}
        </div>
      </div>
    );
  }

  return (
    <div className={cn("relative min-w-0", classNameProp)}>
      {statusSlot}
      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={cn(triggerClasses, "w-[min(100%,18rem)] max-w-full px-2.5")}
            data-phase-indicator={variantProp}
            aria-label={`Deployment phase: ${current.shortLabel} ${current.label}. Open phase list.`}
          >
            <span className="min-w-0">{label}</span>
            <ChevronDown className="size-3.5 shrink-0 text-ink-500" aria-hidden />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-[min(100vw,22rem)] p-0" align="start" sideOffset={6}>
          <div className="p-3">
            <PopoverHeader>
              <PopoverTitle>Deployment phase</PopoverTitle>
            </PopoverHeader>
            {stepper}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
