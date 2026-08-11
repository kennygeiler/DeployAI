# Design Reference: Beautiful UI

Source: https://beautiful-ui-five.vercel.app/ (showcase by turbodesign.co — visual reference to
replicate, not an installable package). Tokens below extracted from the live site's CSS on 2026-08-11.
This is the guide for the DeployAI web design refresh.

## Design language

- Inter, 14px base. Weight 400 body, 500–600 for emphasis. Numbered section labels in mono.
- Semantic surface ladder: `page` (app background) → `canvas` (content wells) → `surface` (cards) →
  `inset` (nested wells) → `hover` / `hover-2` (interaction states).
- Three ink levels: `ink` (primary), `ink-2` (secondary), `ink-3` (tertiary/disabled).
- Hairline borders everywhere (`line`, `line-strong`); shadows always include a 1px hairline ring.
- Single blue accent + green/orange/red semantic colors, each with a `-tint` background pairing.
- Pill radius on buttons/chips (9999px); cards ~12px; subtle diagonal-stripe texture on page gutters.
- Light and dark are first-class; dark is not inverted-light — it has its own tuned values.

## Tokens (light `:root` / dark `.dark`)

| Token | Light | Dark |
|---|---|---|
| page | #fafafb | #17181a |
| canvas | #f1f2f3 | #1c1d1f |
| surface | #fff | #232427 |
| inset | #f7f8f9 | #1f2022 |
| hover | #f4f5f6 | #2a2b2e |
| hover-2 | #e7e9eb | #313236 |
| ink | #1f2124 | #f2f3f4 |
| ink-2 | #62656b | #a5a8ad |
| ink-3 | #9a9da3 | #6c6f75 |
| line | #ecedef | #2e3033 |
| line-strong | #e0e2e5 | #3a3c40 |
| field | #f2f2f3 | #2b2c2f |
| stripe | #49494913 | #ffffff0e |
| stripe-bg | #f5f5f5 | #1b1c1e |
| accent | #0285ff | #3d9aff |
| accent-ink | #0170dd | #7ec0ff |
| accent-tint | #e9f3ff | #3d9aff29 |
| green | #189a4d | #3dbb72 |
| green-tint | #e8f5ed | #3dbb7224 |
| orange | #ef720c | #f68f3c |
| orange-tint | #fdf1e5 | #f68f3c24 |
| red | #e3474c | #ee5c61 |
| red-tint | #fcecec | #ee5c6124 |
| tooltip-bg | #25272b | #111214 |
| tooltip-fg | #f6f7f8 | #f2f3f4 |

Shadows (light):
- hairline: `0 0 0 1px var(--line)`
- btn: `0 0 0 1px var(--line-strong), 0 1px 2px #1018280d`
- card: `0 0 0 1px var(--line), 0 1px 2px #1018280a, 0 2px 6px #10182808`
- raised: `0 0 0 1px var(--line), 0 2px 10px #0000000b`
- overlay: `0 0 0 1px var(--line), 0 8px 28px #0001`
- inset-field: `inset 0 1px 2px #0000001f`
(dark variants use heavier alpha blacks; see site.)

**WCAG note:** `ink-3` (#9a9da3 on #fff ≈ 2.7:1) fails AA — reserve it for disabled/decorative text
only and exclude it from the design-tokens contrast-tested pairs, or darken our variant. `ink-2`
(#62656b ≈ 5.9:1) passes. The design-tokens package's AA contrast tests remain the gate.

## Component patterns → DeployAI mapping

| Beautiful UI pattern | What it is | DeployAI surface |
|---|---|---|
| 01 Loading State | pixel-grid shimmer loader + elapsed time | all loading states; Kenny "working" indicator |
| 02 Thinking | expandable trace — steps/reasoning/search chips | OracleChat reasoning chips (SSE `thinking` frames) |
| 03 Streaming Text | streamed answer, inline numbered sources, follow-ups | OracleChat answers — citations as inline source chips w/ popover; follow-up suggestions |
| 04 Approval Card | agent asks before acting; option buttons | HITL approval card (build component now; wired by ticket D4) |
| 05 Tool Chips | tool calls as compact expandable chips w/ status | Kenny `tool_call`/`tool_result` frames |
| 06 Task Rows | live agent task status rows (running/failed/done) | proposal batch progress; embedding/ingest job status |
| 07 Chat | tabbed chat panel, reasoning replies, composer | OracleChat container |
| 08 Prompt Bar | composer w/ @ sources, / commands, model picker | chat composer (source-mention = engagement scoping later) |
| 09 Recommendation Card | suggestion + confidence meter + accept/alternatives | matrix proposals (MatrixProposals) |
| 10 Context Cards | retrieved chunks with source-type badges | citation evidence panel / provenance |
| 11 Diff Table | AI-proposed edits across tabular data | bulk proposal review diffs |
| 12 Records Table | CRM grid: tags, last interaction, connection strength | stakeholders + engagements list (DRM core view) |
| 13 Filter Table | filterable grid | ledger timeline filters |
| 14 Sidebar Nav | sectioned nav w/ active pill | StrategistNav |
| 15 Search | command-palette search | /search page |
| 16 Insight Cards | metric/insight cards | EngagementInsights, admin dashboard cards |
| 17 Code Block | syntax block w/ copy | (low priority) |
| 19 Selection Actions | floating bulk-action bar on selection | bulk proposal accept |

## Constraints for the refresh

1. Map onto the existing token names where possible (`ink-*`, `paper-*` → surface ladder); the
   design-tokens package's contrast tests (`tokens.test.ts`, WCAG AA ≥4.5:1) must stay green —
   adjust shades, not the tests (ink-3 exception above).
2. Keep the Okabe-Ito colorblind-safe palette for matrix node/edge categories (dataviz needs
   categorical distinction the BUI palette doesn't provide); restyle chrome around it.
3. No new heavyweight UI deps; extend the existing shadcn-style primitives in `components/ui`.
4. Dark mode via the existing mechanism; both themes tuned per the table above.
5. a11y is a gate: axe/pa11y/storybook-a11y stay green; live regions, keyboard paths preserved.
