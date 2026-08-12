import { describe, expect, it } from "vitest";

import {
  KNOWN_TOUR_TARGETS,
  TOUR_CHAT_OPENED_EVENT,
  TOUR_STEPS,
  TOUR_TURN_DONE_EVENT,
  matchesRoutePattern,
} from "@/lib/tour/steps";

describe("TOUR_STEPS integrity", () => {
  it("has the expected step count", () => {
    expect(TOUR_STEPS).toHaveLength(11);
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
