/**
 * Wave 3 K6 — guided demo tour: the typed step list.
 *
 * The tour spotlights the next action on the real product (no screenshots,
 * no fake data) and advances when the visitor actually performs it — but
 * performing it is never required: Next always advances, navigating to the
 * incoming step's `route` and activating its Brief `tab` when needed
 * (tour-ux). Steps reference `data-tour` attributes placed on the live
 * components; a step whose target is `null` (or whose target is not
 * currently in the DOM) renders as a centered popover.
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
  /**
   * Route pattern this step's content lives on. When Next activates the step
   * and the current pathname doesn't match, the tour itself navigates there
   * (see `resolveTourStepPushPath`) — Next always advances, never dead-ends.
   * The Acme sentinel resolves to the visitor's sandbox; absent → the step
   * works from wherever the visitor already is.
   */
  route?: string;
  /**
   * Brief tab that owns this step's target. On activation the tour dispatches
   * TOUR_OPEN_TAB_EVENT (retrying until the target mounts) so below-the-fold
   * tab panels are switched + scrolled into view without the visitor hunting.
   */
  tab?: string;
  /** Optional question the "Use this question" button prefills. */
  prefill?: string;
  /**
   * Optional artifact the popover's button loads into the Capture box
   * (fetched from `url`, dispatched via the capture-prefill event so the
   * visitor still presses Capture themselves — the tour never fakes a click).
   */
  capturePrefill?: { url: string; source: string; label: string };
  /** Optional file download link rendered in the popover (drag-drop beats). */
  download?: { href: string; label: string };
};

/** Non-httpOnly cookie set by /api/auth/demo — the tour's mount switch. */
export const TOUR_COOKIE = "demo_tour";

/**
 * Non-httpOnly cookie set by /api/auth/demo alongside TOUR_COOKIE: the id of
 * THIS visitor's private sandbox engagement (minted per session by the CP so
 * concurrent visitors never share the slip act's deal). Read client-side by
 * the tour and server-side by the BFF engagements list filter.
 */
export const DEMO_ENGAGEMENT_COOKIE = "demo_engagement";

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
 * Catch-the-slip act (K7): `tour-capture-prefill` is dispatched by the tour
 * popover's artifact button and handled by CaptureIngest (detail:
 * `{ text: string; source: string }`); `tour-capture-done` is emitted by
 * CaptureIngest when a capture finishes extracting (detail:
 * `{ proposalCount: number }`) so capture steps advance on the real
 * state change, not on a timer.
 */
export const TOUR_CAPTURE_PREFILL_EVENT = "deployai:tour-capture-prefill";
export const TOUR_CAPTURE_DONE_EVENT = "deployai:tour-capture-done";

/**
 * tour-ux — `tour-open-tab` is dispatched by the TourProvider when a
 * tab-scoped step activates and handled by EngagementBrief (detail:
 * `{ tab: string }`). It drives the same controlled-Tabs setter the KennyAsks
 * "Open Capture" remedy uses, exposed as an event because the tour lives in
 * the layout, outside the Brief's tree.
 */
export const TOUR_OPEN_TAB_EVENT = "deployai:tour-open-tab";

/**
 * The stable Acme engagement id (mirrors ACME_ENGAGEMENT_ID in the CP's
 * demo_reset_internal.py). Used as a route-pattern SENTINEL in TOUR_STEPS
 * and as the fallback when no per-guest sandbox cookie is present (presenter
 * flows and local dev use the stable engagement directly): at runtime the
 * TourProvider swaps it for the visitor's own sandbox path via
 * `resolveTourRoutePattern`, so the slip act only starts once the visitor is
 * on THEIR cold-start deal.
 */
export const ACME_ENGAGEMENT_PATH = "/engagements/acacacac-acac-4aca-8aca-acacacacacac";

/**
 * The seeded BlueState fixture — the corpus the early tour beats (delta,
 * ask, citations, trap) rely on. These steps must route HERE, not to the
 * visitor's empty sandbox: pushing the parameterized pattern through the
 * sandbox fallback sent Next to an engagement with no ledger, where every
 * corpus beat degrades to a refusal.
 */
export const BLUESTATE_ENGAGEMENT_PATH = "/engagements/dddddddd-dddd-4ddd-8ddd-dddddddddddd";

/** Loose UUID shape — guards against a mangled cookie becoming a path segment. */
const UUID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * The demo engagement path for THIS visitor: their sandbox (from the
 * `demo_engagement` cookie) when present and well-formed, else the stable
 * Acme path. `cookieString` is `document.cookie` — passed in so the logic
 * stays testable outside a browser.
 */
export function resolveDemoEngagementPath(cookieString: string): string {
  const found = cookieString
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${DEMO_ENGAGEMENT_COOKIE}=`));
  const id = found ? decodeURIComponent(found.slice(DEMO_ENGAGEMENT_COOKIE.length + 1)) : null;
  return id && UUID_SHAPE.test(id) ? `/engagements/${id}` : ACME_ENGAGEMENT_PATH;
}

/**
 * Resolve a step's route pattern at runtime: the Acme sentinel becomes the
 * visitor's sandbox path; every other pattern passes through unchanged.
 */
export function resolveTourRoutePattern(pattern: string, cookieString: string): string {
  return pattern === ACME_ENGAGEMENT_PATH ? resolveDemoEngagementPath(cookieString) : pattern;
}

/**
 * The concrete path Next pushes when a step's `route` doesn't match the
 * current pathname: the Acme sentinel becomes the visitor's sandbox, and a
 * parameterized pattern (`:engagementId`) also falls back to the sandbox path
 * — the engagement Brief is the only parameterized route the tour visits, and
 * the sandbox is the one deal every guest is guaranteed to have.
 */
export function resolveTourStepPushPath(route: string, cookieString: string): string {
  const resolved = resolveTourRoutePattern(route, cookieString);
  const hasParam = resolved.split("/").some((seg) => seg.startsWith(":"));
  return hasParam ? resolveDemoEngagementPath(cookieString) : resolved;
}

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
    action: "Click the top deal to open its Brief — or press Next and the tour takes you there.",
    advanceOn: { type: "route", pattern: "/engagements/:engagementId" },
  },
  {
    id: "brief-delta",
    target: "brief-delta",
    route: BLUESTATE_ENGAGEMENT_PATH,
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
    route: BLUESTATE_ENGAGEMENT_PATH,
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
    route: BLUESTATE_ENGAGEMENT_PATH,
    tab: "capture",
    title: "Feed it",
    body:
      "This is where raw reality enters the record. Paste a real email thread or a meeting " +
      "note and watch extraction propose memory — decisions, risks, commitments — each one " +
      "queued for the human gate you just saw.",
    action: "Paste any thread and hit Capture — or press Next to continue the tour.",
    advanceOn: { type: "manual" },
  },
  {
    id: "ask-kenny",
    target: "ask-kenny-bar",
    route: BLUESTATE_ENGAGEMENT_PATH,
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
    route: BLUESTATE_ENGAGEMENT_PATH,
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
    route: BLUESTATE_ENGAGEMENT_PATH,
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
    route: BLUESTATE_ENGAGEMENT_PATH,
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
    action:
      "Close the chat, then open Review inbox from the left nav — or press Next to skip ahead.",
    advanceOn: { type: "route", pattern: "/review" },
  },
  {
    id: "graph-tab",
    target: "brief-graph-tab",
    route: BLUESTATE_ENGAGEMENT_PATH,
    title: "The deployment matrix",
    body:
      "Back on a deal, the Graph tab is the accumulated map: stakeholders, systems, decisions, " +
      "risks, and commitments — every node traceable to the event that created it.",
    action: "Click the Graph tab on the Brief — or press Next to move on.",
    advanceOn: { type: "click-target" },
  },
  // --- Catch-the-slip act (K7): one week of a deal, played by the visitor.
  // Monday feeds the record, midweek a commitment quietly moves, Friday the
  // record answers for it — over artifacts the visitor captured themselves.
  {
    id: "slip-week-intro",
    target: null,
    title: "Now play a week for real",
    body:
      "You've seen the loop — now live it. You're the deployment strategist on Acme " +
      "Robotics. It's Monday, the kickoff just ended, and by Friday something in this deal " +
      "will quietly move. Your job is to catch it.",
    action:
      "Open Engagements in the left nav and click Acme Robotics — Pilot Deployment — " +
      "or press Next to jump straight in.",
    advanceOn: { type: "route", pattern: ACME_ENGAGEMENT_PATH },
  },
  {
    id: "slip-monday-kickoff",
    target: "capture-input",
    route: ACME_ENGAGEMENT_PATH,
    tab: "capture",
    title: "Monday — feed it the kickoff",
    body:
      "This deal is empty: no record, no memory. This morning's kickoff transcript is your " +
      "first artifact. Load it, hit Capture, and watch extraction turn 45 minutes of talk " +
      "into proposed memory — Saving, then Extracting, then a queue of proposals.",
    action: 'Click "Load the kickoff transcript", then hit Capture.',
    capturePrefill: {
      url: "/demo/kickoff-transcript.txt",
      source: "meeting_note",
      label: "Load the kickoff transcript",
    },
    advanceOn: { type: "event", name: TOUR_CAPTURE_DONE_EVENT },
  },
  {
    id: "slip-monday-gate",
    target: "brief-needs-you",
    route: ACME_ENGAGEMENT_PATH,
    title: "Nothing enters without you",
    body:
      "Every decision, risk, and commitment extraction found now waits on your accept or " +
      "reject — the record holds only what a human let in. And Kenny is already asking for " +
      "what's missing: the record knows its own gaps before you do.",
    action: "Accept a few proposals, glance at what Kenny asks for, then hit Next.",
    advanceOn: { type: "manual" },
  },
  {
    id: "slip-midweek-email",
    target: "capture-input",
    route: ACME_ENGAGEMENT_PATH,
    tab: "capture",
    title: "Wednesday — a routine email lands",
    body:
      "An end-of-day roundup from ops: AP installs, visitor-day logistics, a dashboard " +
      "request. Ordinary — except one sentence, buried mid-paragraph, quietly moves a " +
      "committed date. Would you catch it on a busy Wednesday?",
    action: 'Click "Load Wednesday\'s email", then Capture it.',
    capturePrefill: {
      url: "/demo/slip-email.txt",
      source: "email",
      label: "Load Wednesday's email",
    },
    advanceOn: { type: "event", name: TOUR_CAPTURE_DONE_EVENT },
  },
  {
    id: "slip-midweek-caught",
    target: "brief-needs-you",
    route: ACME_ENGAGEMENT_PATH,
    title: "It caught the slip",
    body:
      "There it is in the queue: the safety certification package moved October 3 → " +
      "October 17, extracted from one buried sentence and standing right next to the " +
      "original commitment it contradicts. Accept it — the slip is now on the record, with " +
      "evidence.",
    action: "Accept the date-change proposal, then hit Next.",
    advanceOn: { type: "manual" },
  },
  {
    id: "slip-thursday-standup",
    target: "capture-input",
    route: ACME_ENGAGEMENT_PATH,
    tab: "capture",
    title: "Thursday — attach the standup notes",
    body:
      "Thursday's standup recording produced a .vtt transcript — the kind of file that " +
      "usually dies in a folder. One click attaches it: the cue-timing machinery strips " +
      "away, it lands as clean text, and extraction flags a blocker threatening the very " +
      "milestone that just slipped.",
    action: 'Click "Attach the standup notes", then hit Capture.',
    capturePrefill: {
      url: "/demo/acme-standup.vtt",
      source: "meeting_note",
      label: "Attach the standup notes",
    },
    download: { href: "/demo/acme-standup.vtt", label: "or download acme-standup.vtt yourself" },
    advanceOn: { type: "event", name: TOUR_CAPTURE_DONE_EVENT },
  },
  {
    id: "slip-friday-digest",
    target: "brief-delta",
    route: ACME_ENGAGEMENT_PATH,
    title: "Friday — the week, replayed",
    body:
      '"Since you last looked" now tells the story you just lived: a kickoff\'s worth of ' +
      "memory, a slipped date, a new blocker — every entry traceable to an artifact you fed " +
      "in yourself. This is what a returning strategist sees instead of re-reading threads.",
    action: "Scan the week's changes, then hit Next.",
    advanceOn: { type: "manual" },
  },
  {
    id: "slip-friday-ask",
    target: "ask-kenny-bar",
    route: ACME_ENGAGEMENT_PATH,
    title: "The Friday question",
    body:
      "Now the payoff. Ask the question a VP would ask you — and watch Kenny weave the " +
      "kickoff's original date, Wednesday's buried slip, and Thursday's blocker into one " +
      "answer, every claim carrying a citation chip back to what you captured.",
    action: 'Click "Use this question", then hit Ask.',
    advanceOn: { type: "event", name: TOUR_CHAT_OPENED_EVENT },
    prefill: "Are we on track for the safety certification?",
  },
  {
    id: "slip-friday-answer",
    target: null,
    route: ACME_ENGAGEMENT_PATH,
    title: "Caught, cited, on the record",
    body:
      "The answer isn't a vibe — it's the record: committed for October 3, moved to " +
      "October 17 by a buried sentence, now blocked by firmware faults. Three artifacts you " +
      "captured yourself, woven into one cited answer. That's the product.",
    action: "Wait for the answer, then click a citation chip to inspect the evidence.",
    advanceOn: { type: "event", name: TOUR_TURN_DONE_EVENT },
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
