/**
 * Wave 5 GA2 — "Kenny asks" gap-detection types.
 *
 * Mirrors CP `GET /internal/v1/engagements/{id}/gap-asks`. Ask ids are
 * deterministic per (rule, target), so dismissals recorded through the BFF
 * survive recomputes.
 */

export type GapAskRemedyKind = "capture" | "forward" | "answer";

export type GapAsk = {
  id: string;
  rule: string;
  severity: "high" | "medium" | "low";
  target_node_id: string | null;
  title: string;
  why: string;
  remedy_kind: GapAskRemedyKind;
};

export type GapAsksResponse = {
  asks: GapAsk[];
};

export type GapAskDismissal = {
  ask_id: string;
  dismissed_at: string;
  snooze_until: string | null;
};
