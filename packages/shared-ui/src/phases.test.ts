import { describe, expect, it } from "vitest";

import { DEPLOYMENT_PHASES, isDeploymentPhaseId, phaseIndex } from "./phases";

describe("phases", () => {
  it("isDeploymentPhaseId accepts canon IDs", () => {
    expect(isDeploymentPhaseId("P5_pilot")).toBe(true);
    expect(isDeploymentPhaseId("nope")).toBe(false);
  });

  it("phaseIndex matches DEPLOYMENT_PHASES order", () => {
    expect(phaseIndex("P1_pre_engagement")).toBe(0);
    expect(phaseIndex("P7_inheritance")).toBe(DEPLOYMENT_PHASES.length - 1);
  });
});
