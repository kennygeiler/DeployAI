# Story 7-6 — `InMeetingAlertCard` (done)

**Package:** `packages/shared-ui` — `InMeetingAlertCard` (FR36, UX-DR9). `role="complementary"` + `aria-label="In-meeting alert"`, default 360×240, peek 40×40, position `tenant:<uuid>:alert:position` in `localStorage` as `{ left, top }`. **Cmd+\\** / **Ctrl+\\** expands and focus-traps; **Esc** collapses; header pointer-drag + **Alt+Arrow** moves (UX-DR26). States: `archived` → `null`. Vitest: `InMeetingAlertCard.test.tsx`. Storybook: `apps/web/src/stories/Components/InMeetingAlertCard.stories.tsx`.

**Follow-up (Epic 8/9):** wire meeting detection, Oracle payloads, and ≤8s latency; not-now tray; replace citation placeholders with real `CitationChip` rows.
