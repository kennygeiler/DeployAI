import { describe, expect, it } from "vitest";
import { decideSync } from "../src/stub-resolver.js";

describe("stubAuthzResolver", () => {
  it("allows platform admin to view runs", () => {
    const d = decideSync(
      { role: "platform_admin" },
      "ingest:view_runs",
      { kind: "ingestion_runs" },
    );
    expect(d).toEqual({ allow: true });
  });

  it("denies external auditor from schema promotion", () => {
    const d = decideSync(
      { role: "external_auditor" },
      "admin:promote_schema",
      { kind: "schema_proposals" },
    );
    expect(d.allow).toBe(false);
  });
});
