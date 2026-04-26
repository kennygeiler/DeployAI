import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentOutageBanner } from "./AgentOutageBanner";

describe("AgentOutageBanner", () => {
  it("uses status role for informational", () => {
    const { container } = render(
      <AgentOutageBanner
        agentName="Cartographer"
        message="Sync lag ~20s. Retrieval may be slightly stale."
        variant="informational"
      />,
    );
    expect(container.querySelector('[role="status"]')).toBeTruthy();
  });

  it("uses alert role for hard outage", () => {
    const { container } = render(
      <AgentOutageBanner
        agentName="Oracle"
        message="Service unavailable. Memory-only mode."
        variant="alert"
      />,
    );
    expect(container.querySelector('[role="alert"]')).toBeTruthy();
  });
});
