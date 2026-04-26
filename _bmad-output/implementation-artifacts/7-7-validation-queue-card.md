# Story 7-7 — `ValidationQueueCard` (done)

**Package:** `packages/shared-ui` — `ValidationQueueCard` (`<article>`, `aria-labelledby`). `supportingEvidence` is a `ReactNode` (typically 1–3 `CitationChip`s). **Modify** and **Reject** validate non-empty `responseReason` before calling handlers (FR33 / Oracle re-rank). **Confirm** and **Defer** do not require a reason. Vitest: `ValidationQueueCard.test.tsx`. Storybook: `apps/web/src/stories/Components/ValidationQueueCard.stories.tsx`.

**Follow-up (Epic 9):** wire to Master Strategist proposal payloads, assignment, and chair escalation APIs.
