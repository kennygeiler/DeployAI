import { describe, expect, it } from "vitest";

import {
  deSnakeKind,
  displayNameForPerson,
  humanSourceKindLabel,
  initialsFor,
  shortId,
  sourceKindBucket,
  sourceKindIconName,
  stripRedundantKindPrefix,
} from "@/lib/labels";

describe("humanSourceKindLabel", () => {
  it("maps known kinds to short human labels", () => {
    expect(humanSourceKindLabel("risk_closed")).toBe("Risk closed");
    expect(humanSourceKindLabel("oracle_chat_turn")).toBe("Agent answer");
    expect(humanSourceKindLabel("email_ingest")).toBe("Email imported");
    expect(humanSourceKindLabel("proposal_accepted")).toBe("Proposal accepted");
  });

  it("falls back to de-snake-cased sentence case for unknown kinds", () => {
    expect(humanSourceKindLabel("weird_new_kind")).toBe("Weird new kind");
    expect(humanSourceKindLabel("SHOUTY-THING")).toBe("Shouty thing");
  });

  it("handles empty input", () => {
    expect(humanSourceKindLabel("")).toBe("Event");
    expect(humanSourceKindLabel("  ")).toBe("Event");
  });
});

describe("deSnakeKind", () => {
  it("de-snakes and sentence-cases", () => {
    expect(deSnakeKind("matrix_node_created")).toBe("Matrix node created");
  });
});

describe("sourceKindBucket", () => {
  it("mirrors the backend buckets", () => {
    expect(sourceKindBucket("decision_accepted")).toBe("decision");
    expect(sourceKindBucket("risk_closed")).toBe("risk");
    expect(sourceKindBucket("member_added")).toBe("stakeholder");
    expect(sourceKindBucket("stakeholder_added")).toBe("stakeholder");
    expect(sourceKindBucket("commitment_recorded")).toBe("commitment");
    expect(sourceKindBucket("followup_task_created")).toBe("commitment");
    expect(sourceKindBucket("llm_proposal_created")).toBe("proposal");
    expect(sourceKindBucket("oracle_chat_turn")).toBe("agent");
    expect(sourceKindBucket("settings_change")).toBe("system");
    expect(sourceKindBucket("email_ingest")).toBe("other");
  });
});

describe("sourceKindIconName", () => {
  it("maps kinds to icon names with a document fallback", () => {
    expect(sourceKindIconName("email_ingest")).toBe("mail");
    expect(sourceKindIconName("matrix_node_created")).toBe("graph");
    expect(sourceKindIconName("nonexistent")).toBe("document");
  });
});

describe("stripRedundantKindPrefix", () => {
  it("strips a duplicated human-label prefix", () => {
    expect(stripRedundantKindPrefix("Risk closed: stakeholder spec-gap", "risk_closed")).toBe(
      "stakeholder spec-gap",
    );
  });

  it("strips a duplicated raw-kind prefix", () => {
    expect(stripRedundantKindPrefix("risk_closed: stakeholder spec-gap", "risk_closed")).toBe(
      "stakeholder spec-gap",
    );
  });

  it("is case-insensitive and tolerates dash separators", () => {
    expect(stripRedundantKindPrefix("RISK CLOSED — spec-gap", "risk_closed")).toBe("spec-gap");
  });

  it("leaves unrelated titles alone", () => {
    expect(stripRedundantKindPrefix("Budget approved by CFO", "decision_accepted")).toBe(
      "Budget approved by CFO",
    );
  });

  it("keeps the human label when the title is only the kind", () => {
    expect(stripRedundantKindPrefix("risk closed", "risk_closed")).toBe("Risk closed");
  });
});

describe("people helpers", () => {
  it("prefers display_name, then email, then short id", () => {
    expect(
      displayNameForPerson({ display_name: "Ada Lovelace", email: "a@b.co", user_id: "u-1" }),
    ).toBe("Ada Lovelace");
    expect(displayNameForPerson({ email: "a@b.co", user_id: "u-1" })).toBe("a@b.co");
    expect(displayNameForPerson({ user_id: "0a1b2c3d-4444-5555-6666-777788889999" })).toBe(
      "0a1b2c3d…",
    );
    expect(displayNameForPerson({})).toBe("Unknown");
  });

  it("builds initials from names and emails", () => {
    expect(initialsFor("Ada Lovelace")).toBe("AL");
    expect(initialsFor("ada")).toBe("AD");
    expect(initialsFor("ada.lovelace@example.com")).toBe("AC");
    expect(initialsFor("")).toBe("?");
  });

  it("shortens long ids only", () => {
    expect(shortId("abcd")).toBe("abcd");
    expect(shortId("0a1b2c3d4e5f")).toBe("0a1b2c3d…");
  });
});
