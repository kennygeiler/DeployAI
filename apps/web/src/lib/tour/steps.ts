/**
 * Wave 3 K6 — guided demo tour: the typed step list.
 *
 * The tour spotlights the next action on the real product (no screenshots,
 * no fake data) and advances when the visitor actually performs it. Steps
 * reference `data-tour` attributes placed on the live components; a step
 * whose target is `null` (or whose target is not currently in the DOM)
 * renders as a centered popover with a manual Next escape hatch.
 */

/** How a step advances to the next one. */
export type TourAdvance =
  | { type: "click-target" }
  | { type: "route"; pattern: string }
  | { type: "event"; name: string }
  | { type: "manual" };

export type TourStep = {
  /** Stable id — used for keys and analytics; must be unique. */
  id: string;
  /** `data-tour` attribute value to spotlight, or null for a centered card. */
  target: string | null;
  title: string;
  /** 2–3 sentences: what the visitor is looking at. */
  body: string;
  /** Imperative one-liner: the next thing to do. */
  action: string;
  advanceOn: TourAdvance;
  /** Optional question the "Use this question" button prefills. */
  prefill?: string;
};

/** Non-httpOnly cookie set by /api/auth/demo — the tour's mount switch. */
export const TOUR_COOKIE = "demo_tour";

/** sessionStorage keys — dismissal + resume-at-step survive navigation. */
export const TOUR_DISMISSED_KEY = "deployai:tour-dismissed";
export const TOUR_STEP_KEY = "deployai:tour-step";

/**
 * CustomEvent names. `tour-prefill` is dispatched by the tour popover and
 * handled by AskKennyBar (detail: `{ question: string }`); `tour-chat-opened`
 * is emitted by AskKennyBar when the chat overlay mounts; `turn-done` is
 * emitted by OracleChat when a chat turn completes.
 */
export const TOUR_PREFILL_EVENT = "deployai:tour-prefill";
export const TOUR_CHAT_OPENED_EVENT = "deployai:tour-chat-opened";
export const TOUR_TURN_DONE_EVENT = "deployai:turn-done";

/**
 * Every `data-tour` value that exists in the codebase. The steps-integrity
 * test asserts each step target is one of these, so a renamed attribute
 * fails loudly instead of silently degrading every spotlight to a centered
 * popover.
 */
export const KNOWN_TOUR_TARGETS = [
  "portfolio-row",
  "brief-delta",
  "brief-needs-you",
  "capture-input",
  "ask-kenny-bar",
  "oracle-citations",
  "nav-review",
  "brief-graph-tab",
  "nav-overview",
] as const;

export type KnownTourTarget = (typeof KNOWN_TOUR_TARGETS)[number];

export const TOUR_REPO_URL = "https://github.com/kennygeiler/DeployAI";

/**
 * Match a pathname against a route pattern. Segments must align exactly;
 * a `:param` segment matches any single non-empty segment.
 */
export function matchesRoutePattern(pathname: string, pattern: string): boolean {
  const clean = (s: string) => s.split(/[?#]/)[0]!.split("/").filter(Boolean);
  const pathSegs = clean(pathname);
  const patSegs = clean(pattern);
  if (pathSegs.length !== patSegs.length) return false;
  return patSegs.every((seg, i) => (seg.startsWith(":") ? true : seg === pathSegs[i]));
}

export const TOUR_STEPS: readonly TourStep[] = [
  {
    id: "portfolio-open-deal",
    target: "portfolio-row",
    title: "Your portfolio",
    body:
      "Every deal your team is running, ranked by what needs attention — pending proposals, " +
      "open escalations, and silence float a deal to the top. This demo workspace is seeded " +
      "with a real 26-week deployment corpus.",
    action: "Click the top deal to open its Brief.",
    advanceOn: { type: "route", pattern: "/engagements/:engagementId" },
  },
  {
    id: "brief-delta",
    target: "brief-delta",
    title: "Since you last looked",
    body:
      "The Brief opens with what changed while you were gone — new decisions, risks, and " +
      "commitments extracted from emails, meetings, and notes. No re-reading threads to catch up.",
    action: "Scan the recent changes, then hit Next.",
    advanceOn: { type: "manual" },
  },
  {
    id: "brief-needs-you",
    target: "brief-needs-you",
    title: "Needs you — the human gate",
    body:
      "Nothing enters the deal record without a human. Extraction proposals wait here for " +
      "accept/reject, and escalations land in the Review Inbox. The AI proposes; you decide.",
    action: "Note what's waiting on you, then hit Next.",
    advanceOn: { type: "manual" },
  },
  {
    id: "capture-paste",
    target: "capture-input",
    title: "Feed it",
    body:
      "This is where raw reality enters the record. Paste a real email thread or a meeting " +
      "note and watch extraction propose memory — decisions, risks, commitments — each one " +
      "queued for the human gate you just saw.",
    action: "Open the Capture tab and paste any thread — or press Next to continue the tour.",
    advanceOn: { type: "manual" },
  },
  {
    id: "ask-kenny",
    target: "ask-kenny-bar",
    title: "Ask Agent Kenny",
    body:
      "This bar is the front door to an agent that answers only from this deal's ledger — " +
      "every claim is grounded in a real event. Try a question about a decision it has evidence for.",
    action: 'Click "Use this question" below, then hit Ask.',
    advanceOn: { type: "event", name: TOUR_CHAT_OPENED_EVENT },
    prefill: 'What led to the decision "Engagement model: 26-week phased build"?',
  },
  {
    id: "watch-it-think",
    target: null,
    title: "Watch it think",
    body:
      "Kenny is querying the deal ledger right now — the trace shows each thinking step and " +
      "tool call as it happens. Nothing is prebaked; this is a live agent run.",
    action: "Wait for the answer to finish.",
    advanceOn: { type: "event", name: TOUR_TURN_DONE_EVENT },
  },
  {
    id: "click-citation",
    target: "oracle-citations",
    title: "Every claim carries a citation",
    body:
      "The chips below the answer are verified citations — each one was checked against the " +
      "ledger before the answer shipped. Green means the source event really exists and really " +
      "belongs to this deal.",
    action: "Click a citation chip (or hit Next if none appeared).",
    advanceOn: { type: "click-target" },
  },
  {
    id: "the-trap",
    target: null,
    title: "The trap",
    body:
      "Ask something NOT in this deal — watch it refuse instead of invent. There is no Active " +
      "Directory migration in this corpus, so a grounded agent must say so rather than " +
      "hallucinate one.",
    action: 'Click "Use this question", then Ask — and watch the refusal.',
    advanceOn: { type: "event", name: TOUR_TURN_DONE_EVENT },
    prefill: "What concerns were raised about the Active Directory migration?",
  },
  {
    id: "review-inbox",
    target: "nav-review",
    title: "The Review Inbox",
    body:
      "Everything waiting on a human decision — extraction proposals, escalated questions, " +
      "citation disputes — queues in one place. An empty inbox means the record is caught up; " +
      "open items are exactly the deals that need you.",
    action: "Close the chat, then open Review inbox from the left nav.",
    advanceOn: { type: "route", pattern: "/review" },
  },
  {
    id: "graph-tab",
    target: "brief-graph-tab",
    title: "The deployment matrix",
    body:
      "Back on a deal, the Graph tab is the accumulated map: stakeholders, systems, decisions, " +
      "risks, and commitments — every node traceable to the event that created it.",
    action: "Head back into the deal and click the Graph tab.",
    advanceOn: { type: "click-target" },
  },
  {
    id: "finale",
    target: "nav-overview",
    title: "That's the loop",
    body:
      "Ingest → extract → human review → grounded answers with verified citations. The " +
      "Overview page walks every surface with screenshots, and the repo shows how it's built — " +
      "eval gates, leak tests, and all.",
    action: "Explore on your own, or restart the tour any time.",
    advanceOn: { type: "manual" },
  },
];
