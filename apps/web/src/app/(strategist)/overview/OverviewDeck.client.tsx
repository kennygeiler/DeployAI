"use client";

import Image from "next/image";
import Link from "next/link";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Product-overview slide deck. Full-viewport scroll-snap sections, one
 * product surface per slide: a real screenshot (captured from the seeded
 * BlueState engagements by `scripts/capture-overview.mjs`), what the
 * surface does, and a short numbered "how to use it" tutorial.
 *
 * Navigation: scroll/swipe, the progress dots on the right, or
 * PageUp/PageDown/Arrow keys. The deck is its own scroll container so the
 * snap behavior does not hijack the rest of the app.
 */

type Shot = {
  src: string;
  alt: string;
};

type Slide = {
  id: string;
  /** Short label used by the progress dots. */
  label: string;
  /** Slide heading. */
  title: string;
  /** What the surface does — 2-3 sentences. */
  body: string[];
  /** Numbered "how to use it" steps. */
  howTo?: string[];
  shot?: Shot;
  /** Optional smaller companion screenshot rendered above the main one. */
  secondaryShot?: Shot;
};

const SLIDES: readonly Slide[] = [
  {
    id: "what-deployai-is",
    label: "What DeployAI is",
    title: "What DeployAI is",
    body: [
      "DeployAI is evidence-linked memory for every customer deployment: stakeholders, decisions, risks, and commitments are extracted from real interactions and tied to the ledger events that prove them.",
      "Agent Kenny answers questions about a deal with citations that are verified against that ledger before you see them — when the evidence is missing, he says so instead of bluffing.",
      "Humans stay in the loop: nothing enters the deal record until a strategist accepts it, and every accept, reject, and dispute lands in the audit ledger.",
    ],
  },
  {
    id: "portfolio",
    label: "Portfolio",
    title: "Portfolio",
    body: [
      "The Engagements page is the portfolio view: every deal, ranked by what needs your attention. Pending proposals, open escalations, and long silence float a deal to the top.",
      "Below the table, portfolio insights surface cross-deal patterns — the same risk recurring on two engagements, or a role nobody covers.",
    ],
    howTo: [
      "Open Engagements from the sidebar — it is the app's home page.",
      'Scan the "Needs attention" column; badges like "1 proposal" or "76d silent" explain the ranking.',
      "Expand a Portfolio insight to see which engagements it cites.",
      "Click any row to open that deal's Brief.",
    ],
    shot: {
      src: "/overview/portfolio.png",
      alt: 'Engagements page listing four deals ranked by attention, with needs-attention badges such as "1 proposal" and "76d silent", and a Portfolio insights list flagging recurring risk patterns underneath.',
    },
  },
  {
    id: "brief",
    label: "The Brief",
    title: "The Brief",
    body: [
      'Each engagement opens on the Brief: one page that answers "what changed, what needs me, and where does this deal stand".',
      'The header carries the deal\'s vitals (customer, phase, stakeholder/decision/commitment counts). "Since you last looked" digests everything that happened since your previous visit, and narrative cards summarize people, decisions, risks, and commitments.',
    ],
    howTo: [
      "Click an engagement on the portfolio to open its Brief.",
      'Read "Since you last looked" — risks closed, proposals filed, agent activity — instead of replaying the whole timeline.',
      'Check "Needs you" for anything waiting on a human decision.',
      "Scroll on for insights, recommended next actions, and the deeper tabs (Graph, Timeline, Chat, People, Capture).",
    ],
    shot: {
      src: "/overview/brief-since-you-last-looked.png",
      alt: 'The Brief for the BlueState Health Long-Cycle engagement: header with phase and status chips, a "Since you last looked" digest grouping recent risks, proposals and emails, and People / Decisions narrative cards.',
    },
  },
  {
    id: "capture-review",
    label: "Capture → Review",
    title: "The capture → review loop",
    body: [
      "Emails, meeting transcripts, and notes are imported on the Capture tab; the extraction agent turns them into proposed matrix entities — stakeholders, decisions, risks, commitments — each linked to its source events.",
      'Proposals never enter the deal record silently. They queue in "Needs you" as cards you accept or reject inline, and each verdict is written to the audit ledger.',
    ],
    howTo: [
      'Open a Brief and find the "Needs you" section.',
      "Expand a proposal card to see the extracted entity and its evidence.",
      "Accept it to add the entity to the deployment matrix, or reject it to discard.",
      "To feed the loop, import a new interaction from the Capture tab and watch extraction propose entities from it.",
    ],
    shot: {
      src: "/overview/needs-you-queue.png",
      alt: 'Bayview City engagement Brief showing the "Needs you" queue with one pending extraction proposal — a commitment node titled "System maintainable without Tom\'s personal heroics" — with Accept and Reject buttons.',
    },
  },
  {
    id: "ask-kenny",
    label: "Ask Kenny",
    title: "Ask Kenny",
    body: [
      "Every Brief carries a persistent ask-bar with suggested questions derived from the deal's current state; submitting opens a full-width chat with Agent Kenny.",
      "Kenny answers from the engagement substrate — ledger, matrix, insights — by calling tools you can watch in the reasoning trace, and an adversarial reviewer flags any claim that outruns the evidence.",
      "He does not bluff: answers are grounded in retrieved records, citations are verified before they render, and when the substrate has no answer he says so rather than inventing one.",
    ],
    howTo: [
      'On any Brief, type into "Ask Kenny about this deal…" or tap a suggested question.',
      "Watch the trace while he works — each tool call and its row count appears as a chip.",
      "Read the answer's citation chips; each one was checked against the ledger.",
      "Expand the concerns row (if present) to see what the adversarial reviewer flagged.",
    ],
    secondaryShot: {
      src: "/overview/ask-bar.png",
      alt: 'The Brief\'s sticky ask-bar with the input "Ask Kenny about this deal…", an Ask button, and three suggested question pills derived from the engagement state.',
    },
    shot: {
      src: "/overview/kenny-chat-answer.png",
      alt: 'Agent Kenny chat overlay answering "What led to the identity-provider decision?" with a step-by-step causal chain, a collapsed "Thought for 1s, 8 steps" reasoning trace, and adversarial-review concern notes below the answer.',
    },
  },
  {
    id: "citations",
    label: "Citations",
    title: "Citations and receipts",
    body: [
      "Claims in DeployAI come with receipts. Kenny's answers embed [event:…] and [node:…] markers that render as numbered source chips, verified against the database before display — unverifiable citations are flagged, not hidden.",
      "Every matrix entity keeps the same standard: click a node to open its detail sheet, where the Provenance tab walks the causal chain of ledger events that produced it.",
    ],
    howTo: [
      "Click a node in the deployment matrix (table or graph view).",
      'Open the "Source events" tab for the raw evidence events the entity cites.',
      'Switch to "Provenance" to walk the upstream causal chain — who did what, when, and what it caused.',
      "If a citation looks wrong, dispute it — disputes queue in the Review inbox.",
    ],
    shot: {
      src: "/overview/citation-evidence-panel.png",
      alt: 'Matrix node detail sheet for the "Identity provider: Okta over Auth0" decision, listing 5 cited events, with the Provenance tab open on the accepted-proposal ledger event that created the decision.',
    },
  },
  {
    id: "review-inbox",
    label: "Review inbox",
    title: "Review inbox and the knowledge flywheel",
    body: [
      "The Review inbox is the single human-in-the-loop queue across all engagements: extraction proposals, agent escalations, disputed citations, and commitment check-ins, filterable by kind, status, and engagement.",
      "Every verdict lands in the audit ledger and updates the deal record — so each review makes the substrate richer, which makes Kenny's next answer better. That loop is the knowledge flywheel.",
    ],
    howTo: [
      "Open Review inbox from the sidebar; the badge shows how many items wait.",
      "Filter by kind (escalations, citation disputes, extraction proposals, commitments) or by engagement.",
      "Accept or reject items inline — each decision is written to the audit ledger.",
      "Come back to the Brief afterwards: accepted knowledge is immediately part of the deal narrative.",
    ],
    shot: {
      src: "/overview/review-inbox.png",
      alt: "Review inbox filtered to the Bayview City engagement, showing one open extraction-proposal card with Accept and Reject buttons and filter tabs for escalations, citation disputes, extraction proposals, and commitments.",
    },
  },
  {
    id: "graph-lens",
    label: "Graph lens",
    title: "The graph lens",
    body: [
      "On big engagements the deployment matrix grows to hundreds of nodes, so the graph view opens focused: one node and its 1–2-hop neighborhood instead of the full hairball.",
      "The lens toolbar carries search-to-focus, neighborhood depth, per-type filter chips with counts, and a time slider that rewinds the matrix to any point in the deal's history.",
    ],
    howTo: [
      "On a Brief, switch the Deployment matrix from Table to Graph.",
      "Search a node to re-center the lens on it, and pick 1 or 2 hops of context.",
      "Toggle the type chips (stakeholders, decisions, systems…) to declutter.",
      'Click any node to open its evidence sheet; drag the "Matrix as of" slider to time-travel.',
    ],
    shot: {
      src: "/overview/graph-lens.png",
      alt: "Deployment matrix graph view on the BlueState XL engagement: lens toolbar with node search, 1-hop / 2-hop buttons and type filter chips with counts, plus a focused neighborhood of a compliance stakeholder connected to decision nodes.",
    },
  },
  {
    id: "nav-map",
    label: "Where things live",
    title: "Where things live",
    body: [
      "Everything above hangs off six sidebar destinations. When in doubt, start at Engagements — every deal surface is reachable from its Brief.",
    ],
  },
  {
    id: "run-the-demo",
    label: "Run the demo",
    title: "Run the demo",
    body: [
      "The fastest way to feel the product is the cold-start flow on a fresh tenant: the onboarding wizard configures an LLM provider, creates your first engagement, and can load the seeded BlueState demo scenario in one click.",
      "From there, run the loop you just read about: portfolio → Brief → accept a proposal → ask Kenny and follow his citations.",
    ],
    howTo: [
      "On an empty tenant, /engagements redirects to the onboarding wizard automatically.",
      "Complete the wizard: LLM provider, first engagement, first team member.",
      "Load the BlueState demo scenario from the wizard (or import your own transcript via Capture).",
      "Open the Brief, accept a pending proposal, then ask Kenny what changed.",
    ],
  },
];

/** Sidebar destinations listed on the "Where things live" slide. */
const NAV_MAP: readonly { name: string; description: string }[] = [
  {
    name: "Engagements",
    description: "The portfolio — every deal ranked by attention; each row opens its Brief.",
  },
  { name: "Ask", description: "Global Agent Kenny — pick an engagement and ask from anywhere." },
  {
    name: "Review inbox",
    description: "The human-in-the-loop queue: proposals, escalations, disputes, commitments.",
  },
  { name: "Search", description: "Full-text search across the event ledger." },
  {
    name: "Settings",
    description: "Tenant configuration — LLM provider, API keys, integrations, audit.",
  },
  {
    name: "Admin",
    description: "Read-only telemetry: outbound MCP activity and the Agent Kenny dashboard.",
  },
];

function useActiveSlide(
  deckRef: React.RefObject<HTMLDivElement | null>,
  slideCount: number,
): number {
  const [active, setActive] = React.useState(0);
  React.useEffect(() => {
    const deck = deckRef.current;
    if (!deck) return;
    const sections = Array.from(deck.querySelectorAll<HTMLElement>("[data-slide-index]"));
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const idx = Number(entry.target.getAttribute("data-slide-index"));
            if (!Number.isNaN(idx)) setActive(idx);
          }
        }
      },
      { root: deck, threshold: 0.55 },
    );
    for (const s of sections) observer.observe(s);
    return () => observer.disconnect();
  }, [deckRef, slideCount]);
  return active;
}

export function OverviewDeck() {
  const deckRef = React.useRef<HTMLDivElement | null>(null);
  const active = useActiveSlide(deckRef, SLIDES.length);

  const activeRef = React.useRef(active);
  React.useEffect(() => {
    activeRef.current = active;
  }, [active]);

  const scrollToSlide = React.useCallback((index: number) => {
    const deck = deckRef.current;
    if (!deck) return;
    const clamped = Math.max(0, Math.min(SLIDES.length - 1, index));
    const target = deck.querySelector<HTMLElement>(`[data-slide-index="${clamped}"]`);
    if (!target) return;
    // Programmatic smooth scrolling is swallowed entirely by the mandatory
    // snap container in Chromium (the scroll never starts), so jump
    // instantly — the snap points make an instant jump land cleanly, and it
    // is also the right behavior under prefers-reduced-motion.
    deck.scrollTo({
      top: target.getBoundingClientRect().top - deck.getBoundingClientRect().top + deck.scrollTop,
      behavior: "instant",
    });
  }, []);

  // PageUp/PageDown + arrow keys page through slides. Registered on window
  // (clicks inside the deck do not reliably focus it), guarded so the deck
  // never steals keys from form fields or modified shortcuts. The page has
  // no other scroll surfaces, so owning these keys page-wide is safe.
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target;
      if (
        target instanceof HTMLElement &&
        (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))
      ) {
        return;
      }
      const next = ["PageDown", "ArrowDown", "ArrowRight"].includes(e.key);
      const prev = ["PageUp", "ArrowUp", "ArrowLeft"].includes(e.key);
      if (!next && !prev) return;
      e.preventDefault();
      scrollToSlide(activeRef.current + (next ? 1 : -1));
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [scrollToSlide]);

  return (
    <div className="relative">
      {/* Visible skip affordance: jump straight past the walkthrough. */}
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="text-sm text-ink-600">
          Scroll, use the dots, or press <kbd className="rounded bg-hover px-1">PgDn</kbd> /{" "}
          <kbd className="rounded bg-hover px-1">PgUp</kbd> to move between slides.
        </p>
        <Button
          type="button"
          variant="outline"
          size="xs"
          onClick={() => scrollToSlide(SLIDES.length - 1)}
          className="text-ink-600 hover:text-ink"
        >
          Skip to the end
        </Button>
      </div>

      {/* A keyboard-scrollable region must itself be focusable (WCAG 2.1.1 /
          axe scrollable-region-focusable); jsx-a11y cannot tell this div is
          the scroll container, so the rule is disabled with cause. */}
      {/* eslint-disable jsx-a11y/no-noninteractive-tabindex */}
      <div
        ref={deckRef}
        role="region"
        aria-label="Product overview slides"
        tabIndex={0}
        data-testid="overview-deck"
        className="h-[calc(100dvh-10.5rem)] snap-y snap-mandatory overflow-y-auto scroll-smooth rounded-card focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        {/* eslint-enable jsx-a11y/no-noninteractive-tabindex */}
        {SLIDES.map((slide, i) => (
          <section
            key={slide.id}
            id={slide.id}
            data-slide-index={i}
            aria-label={slide.title}
            className="flex min-h-full snap-start flex-col justify-center gap-5 py-8 pr-10 pl-1"
          >
            {i === 0 ? <HeroSlide slide={slide} onStart={() => scrollToSlide(1)} /> : null}
            {i > 0 ? <ContentSlide slide={slide} index={i} /> : null}
          </section>
        ))}
      </div>

      {/* Progress dots — fixed to the deck's right edge. */}
      <nav aria-label="Slide navigation" className="absolute top-1/2 right-0 z-10 -translate-y-1/2">
        <ol className="flex flex-col gap-2">
          {SLIDES.map((slide, i) => (
            <li key={slide.id}>
              <Button
                type="button"
                variant="ghost"
                onClick={() => scrollToSlide(i)}
                aria-label={`Go to slide ${i + 1}: ${slide.label}`}
                aria-current={active === i ? "true" : undefined}
                title={slide.label}
                className={cn(
                  "block size-2.5 rounded-full p-0 shadow-hairline transition-colors",
                  active === i ? "bg-ink hover:bg-ink" : "bg-hover-2 hover:bg-ink-600",
                )}
              />
            </li>
          ))}
        </ol>
      </nav>
    </div>
  );
}

function HeroSlide({ slide, onStart }: { slide: Slide; onStart: () => void }) {
  return (
    <div className="mx-auto max-w-3xl space-y-6 text-center">
      <p className="font-mono text-xs font-semibold tracking-widest text-ink-600 uppercase">
        Product overview
      </p>
      <h1 className="text-display font-semibold tracking-tight text-ink-950">{slide.title}</h1>
      <div className="space-y-3">
        {slide.body.map((sentence) => (
          <p key={sentence} className="text-base leading-relaxed text-ink-600">
            {sentence}
          </p>
        ))}
      </div>
      <div className="flex items-center justify-center gap-3">
        <Button type="button" onClick={onStart}>
          Start the tour
        </Button>
        <Button asChild variant="outline">
          <Link href="/engagements">Open the portfolio</Link>
        </Button>
      </div>
    </div>
  );
}

function ContentSlide({ slide, index }: { slide: Slide; index: number }) {
  return (
    <div className="mx-auto grid w-full max-w-[1400px] items-center gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="order-2 space-y-3 lg:order-none">
        {slide.secondaryShot ? <ScreenshotCard shot={slide.secondaryShot} compact /> : null}
        {slide.shot ? <ScreenshotCard shot={slide.shot} /> : null}
        {slide.id === "nav-map" ? <NavMapCard /> : null}
      </div>
      <div className="space-y-4">
        <p className="font-mono text-xs font-semibold tracking-widest text-ink-600 uppercase">
          {String(index).padStart(2, "0")} · {slide.label}
        </p>
        <h2 className="text-2xl font-semibold tracking-tight text-ink-950">{slide.title}</h2>
        <div className="space-y-2">
          {slide.body.map((sentence) => (
            <p key={sentence} className="text-sm leading-relaxed text-ink-600">
              {sentence}
            </p>
          ))}
        </div>
        {slide.howTo ? (
          <div className="rounded-card border border-line bg-surface p-4 shadow-hairline">
            <h3 className="text-xs font-semibold tracking-wide text-ink-800 uppercase">
              How to use it
            </h3>
            <ol className="mt-2 list-none space-y-1.5">
              {slide.howTo.map((step, stepIndex) => (
                <li key={step} className="flex gap-2 text-sm leading-relaxed text-ink-600">
                  <span className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-hover font-mono text-[10px] font-semibold text-ink-800 shadow-hairline">
                    {stepIndex + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </div>
        ) : null}
        {slide.id === "run-the-demo" ? (
          <Link
            href="/engagements"
            className="inline-flex rounded-full bg-primary px-5 py-2 text-sm font-medium text-primary-foreground shadow-btn transition-opacity hover:opacity-90 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            Take me there
          </Link>
        ) : null}
      </div>
    </div>
  );
}

function ScreenshotCard({ shot, compact = false }: { shot: Shot; compact?: boolean }) {
  // Screenshots are captured light-mode at 1600x1000 CSS px (2x DPR), so the
  // frame stays theme-neutral: surface card + hairline ring in both themes.
  return (
    <figure
      className={cn(
        "overflow-hidden rounded-card bg-surface p-1.5 ring-1 ring-line shadow-card",
        compact && "max-w-[75%]",
      )}
    >
      <Image
        src={shot.src}
        alt={shot.alt}
        width={1600}
        height={1000}
        unoptimized
        className="h-auto w-full rounded-[calc(var(--radius-card)-4px)] border border-line"
      />
    </figure>
  );
}

function NavMapCard() {
  return (
    <div className="rounded-card border border-line bg-surface p-4 shadow-card">
      <ul className="divide-y divide-line">
        {NAV_MAP.map((item) => (
          <li key={item.name} className="flex gap-4 py-2.5 first:pt-0 last:pb-0">
            <span className="w-32 shrink-0 text-sm font-medium text-ink">{item.name}</span>
            <span className="text-sm leading-relaxed text-ink-600">{item.description}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
