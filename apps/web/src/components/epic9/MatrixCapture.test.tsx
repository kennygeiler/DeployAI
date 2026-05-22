import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MatrixNode } from "@/lib/bff/matrix-types";

import { MatrixCapture } from "./MatrixCapture.client";

function mkNode(id: string, node_type: string, title: string): MatrixNode {
  return {
    id,
    engagement_id: "e1",
    node_type,
    title,
    identity_node_id: null,
    attributes: {},
    status: null,
    evidence_event_ids: [],
    created_at: "2026-05-09T00:00:00Z",
    updated_at: "2026-05-09T00:00:00Z",
  };
}

type Call = { url: string; method: string; body: string };

function recordingFetch(calls: Call[]) {
  return vi.fn((url: string, init?: { method?: string; body?: unknown }) => {
    calls.push({
      url,
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? init.body : "",
    });
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

describe("MatrixCapture", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts a new matrix node from the entity form", async () => {
    const calls: Call[] = [];
    vi.stubGlobal("fetch", recordingFetch(calls));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<MatrixCapture engagementId="e1" nodes={[]} onChanged={onChanged} />);

    await user.selectOptions(screen.getByLabelText("Entity type"), "risk");
    await user.type(screen.getByLabelText("Title"), "Calibration slip");
    await user.click(screen.getByRole("button", { name: "Add entity" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const posted = calls.find((c) => c.method === "POST");
    expect(posted?.url).toContain("/api/bff/engagements/e1/matrix/nodes");
    expect(posted?.body).toContain("Calibration slip");
    expect(posted?.body).toContain("risk");
    expect(onChanged).toHaveBeenCalled();
  });

  it("posts a new matrix edge between two nodes", async () => {
    const calls: Call[] = [];
    vi.stubGlobal("fetch", recordingFetch(calls));
    const user = userEvent.setup();
    render(
      <MatrixCapture
        engagementId="e1"
        nodes={[mkNode("n1", "risk", "Calibration slip"), mkNode("n2", "system", "LiDAR ingest")]}
        onChanged={vi.fn()}
      />,
    );

    await user.selectOptions(screen.getByLabelText("From"), "n1");
    await user.selectOptions(screen.getByLabelText("Relationship"), "threatens");
    await user.selectOptions(screen.getByLabelText("To"), "n2");
    await user.click(screen.getByRole("button", { name: "Add link" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const posted = calls.find((c) => c.method === "POST");
    expect(posted?.url).toContain("/api/bff/engagements/e1/matrix/edges");
    expect(posted?.body).toContain("threatens");
    expect(posted?.body).toContain("n1");
    expect(posted?.body).toContain("n2");
  });

  it("hides the link form until there are at least two nodes", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(
      <MatrixCapture
        engagementId="e1"
        nodes={[mkNode("n1", "risk", "only one")]}
        onChanged={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Add entity" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add link" })).toBeNull();
  });
});
