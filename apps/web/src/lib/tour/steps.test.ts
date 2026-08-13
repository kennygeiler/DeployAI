import { describe, expect, it } from "vitest";

import {
  ACME_ENGAGEMENT_PATH,
  DEMO_ENGAGEMENT_COOKIE,
  KNOWN_TOUR_TARGETS,
  TOUR_CAPTURE_DONE_EVENT,
  TOUR_CHAT_OPENED_EVENT,
  TOUR_STEPS,
  TOUR_TURN_DONE_EVENT,
  matchesRoutePattern,
  resolveDemoEngagementPath,
  resolveTourRoutePattern,
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

  it("wires the ask step to the chat-opened event with the decision prefill", () => {
    const ask = TOUR_STEPS.find((s) => s.id === "ask-kenny");
    expect(ask?.advanceOn).toEqual({ type: "event", name: TOUR_CHAT_OPENED_EVENT });
    expect(ask?.prefill).toBe('What led to the decision "Engagement model: 26-week phased build"?');
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

  it("the standup step offers the .vtt download for the drag-drop beat", () => {
    const step = TOUR_STEPS.find((s) => s.id === "slip-thursday-standup");
    expect(step?.download?.href).toBe("/demo/acme-standup.vtt");
    expect(step?.capturePrefill).toBeUndefined();
    expect(step?.advanceOn).toEqual({ type: "event", name: TOUR_CAPTURE_DONE_EVENT });
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
