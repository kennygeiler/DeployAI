import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EngagementCaptureForm } from "./EngagementCaptureForm.client";

describe("EngagementCaptureForm", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts a log entry with the chosen kind and body to the engagement", async () => {
    const calls: Array<{ url: string; method: string; body: string }> = [];
    const fetchMock = vi.fn((url: string, init?: { method?: string; body?: unknown }) => {
      calls.push({
        url,
        method: init?.method ?? "GET",
        body: typeof init?.body === "string" ? init.body : "",
      });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ entries: [] }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<EngagementCaptureForm engagementId="eng-1" />);

    await user.type(screen.getByLabelText("Entry"), "Calibration slipped a week.");
    await user.click(screen.getByRole("button", { name: /log/i }));

    await waitFor(() => {
      expect(calls.some((c) => c.method === "POST")).toBe(true);
    });
    const posted = calls.find((c) => c.method === "POST");
    expect(posted?.url).toContain("/api/bff/engagements/eng-1/log");
    expect(posted?.body).toContain("Calibration slipped a week.");
    expect(posted?.body).toContain("meeting");
  });
});
