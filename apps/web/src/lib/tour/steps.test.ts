import { describe, expect, it } from "vitest";

import {
  ACME_ENGAGEMENT_PATH,
  BLUESTATE_ENGAGEMENT_PATH,
  DEMO_ENGAGEMENT_COOKIE,
  KNOWN_TOUR_TARGETS,
  TOUR_CAPTURE_DONE_EVENT,
  TOUR_CHAT_OPENED_EVENT,
  TOUR_STEPS,
  TOUR_TURN_DONE_EVENT,
  matchesRoutePattern,
  resolveDemoEngagementPath,
  resolveTourRoutePattern,
  resolveTourStepPushPath,
} from "@/lib/tour/steps";

describe("TOUR_STEPS integrity", () => {
  it("has the expected step count", () => {
    expect(TOUR_STEPS).toHaveLength(20);
  });

  it("has unique ids", () => {
    const ids = TOUR_STEPS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("only references known data-tour targets (or null)", () => {
    const known = new Set<string>(KNOWN_TOUR_TARGETS);
    for (const step of TOUR_STEPS) {
      if (step.target !== null) {
        expect(known.has(step.target), `unknown target "${step.target}" on ${step.id}`).toBe(true);
      }
    }
  });

  it("has non-empty title, body (2+ sentences worth), and imperative action", () => {
    for (const step of TOUR_STEPS) {
      expect(step.title.length, step.id).toBeGreaterThan(0);
      expect(step.body.length, step.id).toBeGreaterThan(40);
      expect(step.action.length, step.id).toBeGreaterThan(0);
    }
  });

  it("route patterns are absolute paths", () => {
    for (const step of TOUR_STEPS) {
      if (step.advanceOn.type === "route") {
        expect(step.advanceOn.pattern.startsWith("/"), step.id).toBe(true);
      }
    }
  });

  it("places the manual capture-paste step right after brief-needs-you", () => {
    const needsYou = TOUR_STEPS.findIndex((s) => s.id === "brief-needs-you");
    const capture = TOUR_STEPS[needsYou + 1]!;
    expect(capture.id).toBe("capture-paste");
    expect(capture.target).toBe("capture-input");
    // Low-friction: manual advance — pasting is optional, Next always works.
    expect(capture.advanceOn).toEqual({ type: "manual" });
  });

  it("wires the ask step to the chat-opened event with the live-proven prefill", () => {
    const ask = TOUR_STEPS.find((s) => s.id === "ask-kenny");
    expect(ask?.advanceOn).toEqual({ type: "event", name: TOUR_CHAT_OPENED_EVENT });
    // Verified on prod to yield a fully cited answer (Raj Patel sponsors-edge
    // + the "Identity provider: Okta over Auth0" decision). The refusal beat
    // is the-trap's job — this step must never prefill a question the corpus
    // cannot answer.
    expect(ask?.prefill).toBe(
      "Who is the executive sponsor and what did we decide about the identity provider?",
    );
  });

  it("wires the trap step to turn-done with the out-of-corpus prefill", () => {
    const trap = TOUR_STEPS.find((s) => s.id === "the-trap");
    expect(trap?.advanceOn).toEqual({ type: "event", name: TOUR_TURN_DONE_EVENT });
    expect(trap?.prefill).toBe("What concerns were raised about the Active Directory migration?");
  });

  it("ends on a manual finale", () => {
    const last = TOUR_STEPS[TOUR_STEPS.length - 1]!;
    expect(last.id).toBe("finale");
    expect(last.advanceOn.type).toBe("manual");
  });

  // tour-ux defect 1 — Next must never dead-end: every step whose content
  // lives on the Brief declares the route Next navigates to.
  it("Brief-bound steps declare a route for Next-navigation", () => {
    const actOne = [
      "brief-delta",
      "brief-needs-you",
      "capture-paste",
      "ask-kenny",
      "watch-it-think",
      "click-citation",
      "the-trap",
      "graph-tab",
    ];
    for (const id of actOne) {
      const step = TOUR_STEPS.find((s) => s.id === id);
      expect(step?.route, id).toBe(BLUESTATE_ENGAGEMENT_PATH);
    }
    for (const step of TOUR_STEPS.filter((s) => s.id.startsWith("slip-"))) {
      if (step.id === "slip-week-intro") continue; // the intro card works anywhere
      expect(step.route, step.id).toBe(ACME_ENGAGEMENT_PATH);
    }
  });

  // demo-polish fix 3 — the chat overlay survives navigation; steps whose
  // Brief target it would cover must declare closeChat so the tour can ask
  // AskKennyBar to close it on activation.
  it("Brief-spotlight steps after the ask beats declare closeChat", () => {
    const needClose = [
      "graph-tab",
      "slip-monday-kickoff",
      "slip-monday-gate",
      "slip-midweek-email",
      "slip-midweek-caught",
      "slip-thursday-standup",
      "slip-friday-digest",
    ];
    for (const step of TOUR_STEPS) {
      if (needClose.includes(step.id)) {
        expect(step.closeChat, step.id).toBe(true);
      } else {
        // Ask/trap steps must NOT close the chat they just opened; the
        // review-inbox beat keeps its "close the chat yourself" copy.
        expect(step.closeChat, step.id).toBeUndefined();
      }
    }
  });

  // tour-ux defect 3 — steps targeting the Capture panel switch its tab.
  it("capture-scoped steps declare the capture tab", () => {
    for (const step of TOUR_STEPS) {
      if (step.target === "capture-input") {
        expect(step.tab, step.id).toBe("capture");
      } else {
        expect(step.tab, step.id).toBeUndefined();
      }
    }
  });
});

describe("catch-the-slip act (K7)", () => {
  const ids = TOUR_STEPS.map((s) => s.id);

  it("sits between the graph tab and the finale, in week order", () => {
    const act = [
      "slip-week-intro",
      "slip-monday-kickoff",
      "slip-monday-gate",
      "slip-midweek-email",
      "slip-midweek-caught",
      "slip-thursday-standup",
      "slip-friday-digest",
      "slip-friday-ask",
      "slip-friday-answer",
    ];
    const start = ids.indexOf("slip-week-intro");
    expect(ids[start - 1]).toBe("graph-tab");
    expect(ids.slice(start, start + act.length)).toEqual(act);
    expect(ids[start + act.length]).toBe("finale");
  });

  it("opens by routing to the Acme-path sentinel (resolved per guest at runtime)", () => {
    const intro = TOUR_STEPS.find((s) => s.id === "slip-week-intro");
    expect(intro?.advanceOn).toEqual({ type: "route", pattern: ACME_ENGAGEMENT_PATH });
    expect(ACME_ENGAGEMENT_PATH).toBe("/engagements/acacacac-acac-4aca-8aca-acacacacacac");
  });

  it("capture steps prefill a real artifact and advance on the capture-done event", () => {
    const expected: Record<string, { url: string; source: string }> = {
      "slip-monday-kickoff": { url: "/demo/kickoff-transcript.txt", source: "meeting_note" },
      "slip-midweek-email": { url: "/demo/slip-email.txt", source: "email" },
    };
    for (const [id, want] of Object.entries(expected)) {
      const step = TOUR_STEPS.find((s) => s.id === id);
      expect(step?.target, id).toBe("capture-input");
      expect(step?.capturePrefill?.url, id).toBe(want.url);
      expect(step?.capturePrefill?.source, id).toBe(want.source);
      expect(step?.advanceOn, id).toEqual({ type: "event", name: TOUR_CAPTURE_DONE_EVENT });
    }
  });

  it("the standup step attaches the .vtt with one click, download as the secondary path", () => {
    const step = TOUR_STEPS.find((s) => s.id === "slip-thursday-standup");
    // tour-ux defect 4 — the primary path is the one-click attach button
    // (fetched + run through the drop path's parser); the download link
    // stays for visitors who want the file itself.
    expect(step?.capturePrefill?.url).toBe("/demo/acme-standup.vtt");
    expect(step?.capturePrefill?.source).toBe("meeting_note");
    expect(step?.download?.href).toBe("/demo/acme-standup.vtt");
    expect(step?.advanceOn).toEqual({ type: "event", name: TOUR_CAPTURE_DONE_EVENT });
  });

  it("directs the batch accept on the Monday gate and Friday digest (deterministic record)", () => {
    // Partial accepts starve the Friday answer (live QA: "3 commitments,
    // no descriptive detail, 0 edges"). The gate and digest beats both
    // direct "Accept all pending" so the record is deterministically rich.
    for (const id of ["slip-monday-gate", "slip-friday-digest"]) {
      const step = TOUR_STEPS.find((s) => s.id === id);
      expect(step?.action, id).toContain("Accept all pending");
    }
    // The midweek catch stays an explicit single accept — the catch IS the beat.
    const caught = TOUR_STEPS.find((s) => s.id === "slip-midweek-caught");
    expect(caught?.action).toContain("Accept the date-change proposal");
  });

  it("the Friday ask prefills the payoff question", () => {
    const ask = TOUR_STEPS.find((s) => s.id === "slip-friday-ask");
    expect(ask?.advanceOn).toEqual({ type: "event", name: TOUR_CHAT_OPENED_EVENT });
    expect(ask?.prefill).toBe("Are we on track for the safety certification?");
    const answer = TOUR_STEPS.find((s) => s.id === "slip-friday-answer");
    expect(answer?.advanceOn).toEqual({ type: "event", name: TOUR_TURN_DONE_EVENT });
  });
});

describe("per-guest sandbox path resolution", () => {
  const SANDBOX = "55555555-5555-4555-8555-555555555555";

  it("resolves the sandbox path from the demo_engagement cookie", () => {
    const cookie = `demo_tour=1; ${DEMO_ENGAGEMENT_COOKIE}=${SANDBOX}`;
    expect(resolveDemoEngagementPath(cookie)).toBe(`/engagements/${SANDBOX}`);
  });

  it("falls back to the stable Acme path without the cookie", () => {
    expect(resolveDemoEngagementPath("demo_tour=1")).toBe(ACME_ENGAGEMENT_PATH);
    expect(resolveDemoEngagementPath("")).toBe(ACME_ENGAGEMENT_PATH);
  });

  it("rejects a non-UUID cookie value (never becomes a path segment)", () => {
    expect(resolveDemoEngagementPath(`${DEMO_ENGAGEMENT_COOKIE}=..%2Fadmin`)).toBe(
      ACME_ENGAGEMENT_PATH,
    );
    expect(resolveDemoEngagementPath(`${DEMO_ENGAGEMENT_COOKIE}=`)).toBe(ACME_ENGAGEMENT_PATH);
  });

  it("resolveTourRoutePattern swaps only the Acme sentinel", () => {
    const cookie = `${DEMO_ENGAGEMENT_COOKIE}=${SANDBOX}`;
    expect(resolveTourRoutePattern(ACME_ENGAGEMENT_PATH, cookie)).toBe(`/engagements/${SANDBOX}`);
    expect(resolveTourRoutePattern("/engagements/:engagementId", cookie)).toBe(
      "/engagements/:engagementId",
    );
    expect(resolveTourRoutePattern("/review", cookie)).toBe("/review");
  });

  it("resolveTourStepPushPath always yields a concrete, pushable path", () => {
    const cookie = `${DEMO_ENGAGEMENT_COOKIE}=${SANDBOX}`;
    // Sentinel → the visitor's sandbox.
    expect(resolveTourStepPushPath(ACME_ENGAGEMENT_PATH, cookie)).toBe(`/engagements/${SANDBOX}`);
    // Parameterized Brief pattern → the sandbox too (the one deal every
    // guest is guaranteed to have).
    expect(resolveTourStepPushPath("/engagements/:engagementId", cookie)).toBe(
      `/engagements/${SANDBOX}`,
    );
    expect(resolveTourStepPushPath("/engagements/:engagementId", "")).toBe(ACME_ENGAGEMENT_PATH);
    // Literal routes pass through.
    expect(resolveTourStepPushPath("/review", cookie)).toBe("/review");
  });
});

describe("matchesRoutePattern", () => {
  it("matches exact paths", () => {
    expect(matchesRoutePattern("/review", "/review")).toBe(true);
    expect(matchesRoutePattern("/review/", "/review")).toBe(true);
    expect(matchesRoutePattern("/reviews", "/review")).toBe(false);
  });

  it("matches :param segments without over-matching", () => {
    const pattern = "/engagements/:engagementId";
    expect(matchesRoutePattern("/engagements/abc-123", pattern)).toBe(true);
    expect(matchesRoutePattern("/engagements", pattern)).toBe(false);
    expect(matchesRoutePattern("/engagements/abc/timeline", pattern)).toBe(false);
  });

  it("ignores query strings and hashes", () => {
    expect(matchesRoutePattern("/review?engagementId=e1", "/review")).toBe(true);
    expect(matchesRoutePattern("/review#top", "/review")).toBe(true);
  });
});
