import { afterEach, describe, expect, it } from "vitest";

import type { AuthActor } from "@deployai/authz";

import {
  actorIsDeployAiPilotTenant,
  digestSurfacesUseControlPlane,
  eveningSynthesisSurfacesUseControlPlane,
  evidenceSurfacesUseControlPlane,
  phaseTrackingSurfacesUseControlPlane,
} from "./strategist-pilot-tenant";

describe("strategist-pilot-tenant", () => {
  const originalPilot = process.env.DEPLOYAI_PILOT_TENANT_ID;
  const originalDigest = process.env.DEPLOYAI_DIGEST_SOURCE;
  const originalEvidence = process.env.DEPLOYAI_EVIDENCE_SOURCE;
  const originalPhase = process.env.DEPLOYAI_PHASE_TRACKING_SOURCE;
  const originalEvening = process.env.DEPLOYAI_EVENING_SYNTHESIS_SOURCE;

  afterEach(() => {
    for (const [key, val] of [
      ["DEPLOYAI_PILOT_TENANT_ID", originalPilot],
      ["DEPLOYAI_DIGEST_SOURCE", originalDigest],
      ["DEPLOYAI_EVIDENCE_SOURCE", originalEvidence],
      ["DEPLOYAI_PHASE_TRACKING_SOURCE", originalPhase],
      ["DEPLOYAI_EVENING_SYNTHESIS_SOURCE", originalEvening],
    ] as const) {
      if (val === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = val;
      }
    }
  });

  it("matches pilot tenant UUID case-insensitively (JWT tid alignment)", () => {
    process.env.DEPLOYAI_PILOT_TENANT_ID = "22222222-2222-4222-8222-222222222222";
    expect(actorIsDeployAiPilotTenant("22222222-2222-4222-8222-222222222222")).toBe(true);
    expect(actorIsDeployAiPilotTenant("22222222-2222-4222-8222-222222222222".toUpperCase())).toBe(
      true,
    );
    expect(actorIsDeployAiPilotTenant("33333333-3333-4333-8333-333333333333")).toBe(false);
  });

  it("treats string pilot ids case-insensitively", () => {
    process.env.DEPLOYAI_PILOT_TENANT_ID = "Acme-Pilot";
    expect(actorIsDeployAiPilotTenant("acme-pilot")).toBe(true);
  });

  it("short-circuit cp source flags still enable CP without pilot match", () => {
    delete process.env.DEPLOYAI_PILOT_TENANT_ID;
    process.env.DEPLOYAI_DIGEST_SOURCE = "cp";
    const actor: AuthActor = {
      role: "deployment_strategist",
      tenantId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    };
    expect(digestSurfacesUseControlPlane(actor)).toBe(true);
    delete process.env.DEPLOYAI_DIGEST_SOURCE;
    process.env.DEPLOYAI_EVIDENCE_SOURCE = "cp";
    expect(evidenceSurfacesUseControlPlane(actor)).toBe(true);
    delete process.env.DEPLOYAI_EVIDENCE_SOURCE;
    process.env.DEPLOYAI_PHASE_TRACKING_SOURCE = "cp";
    expect(phaseTrackingSurfacesUseControlPlane(actor)).toBe(true);
    delete process.env.DEPLOYAI_PHASE_TRACKING_SOURCE;
    process.env.DEPLOYAI_EVENING_SYNTHESIS_SOURCE = "cp";
    expect(eveningSynthesisSurfacesUseControlPlane(actor)).toBe(true);
  });
});
