# Story 7-5 — `OverrideComposer` (done)

**Package:** `packages/shared-ui` — `OverrideComposer` (`<form>` landmark, labels above fields, `aria-invalid` / `aria-describedby`, `role="alert"` + `aria-live="assertive"` error summary). Evidence as multi-select from `evidenceOptions`; propagation list is **stub** text for Epic 8+ graph binding. **Cmd+Enter** (mac) / **Ctrl+Enter** submits. Vitest: `OverrideComposer.test.tsx`. Storybook: `apps/web/src/stories/Components/OverrideComposer.stories.tsx`.

**Follow-up (Epic 10):** wire `onSubmit` to control-plane override API; replace evidence checkboxes with real citation picker + propagation from memory graph.
