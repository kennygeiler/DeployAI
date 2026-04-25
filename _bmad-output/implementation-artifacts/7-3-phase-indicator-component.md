# Story 7-3 — `PhaseIndicator` (done)

**Package:** `packages/shared-ui` — `PhaseIndicator` (32px trigger, `aria-live="polite"` on phase id change), Radix `Popover` stepper listing all seven phases with prior/next summary, variants `default` | `pending-transition` | `locked` (read-only strip, no popover). Canon phase IDs + labels in `phases.ts` (Epic 5.4 alignment).

**Infra:** `components/ui/popover.tsx` (radix-ui, token classes). Tests: `PhaseIndicator.test.tsx`. Storybook: `apps/web/src/stories/Components/PhaseIndicator.stories.tsx`.

**Follow-up (Epic 8):** mount in nav chrome next to `FreshnessChip`; wire `currentPhaseId` from control plane tenant phase when API exists.
