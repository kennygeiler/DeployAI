import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InteractionImport } from "./InteractionImport.client";

type Call = { url: string; method: string; body: string };

function recordingFetch(calls: Call[]) {
  return vi.fn((url: string, init?: { method?: string; body?: unknown }) => {
    calls.push({
      url,
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? init.body : "",
    });
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ event: {} }) });
  });
}

describe("InteractionImport", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts raw text wrapped as { text: ... } content", async () => {
    const calls: Call[] = [];
    vi.stubGlobal("fetch", recordingFetch(calls));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<InteractionImport engagementId="e1" onChanged={onChanged} />);

    await user.selectOptions(screen.getByLabelText("Source"), "meeting_note");
    await user.type(screen.getByLabelText("Content (text or JSON)"), "Calibration walkthrough.");
    await user.click(screen.getByRole("button", { name: "Import" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const posted = calls.find((c) => c.method === "POST")!;
    expect(posted.url).toContain("/api/bff/engagements/e1/ingest");
    const parsed = JSON.parse(posted.body) as {
      source: string;
      content: Record<string, unknown>;
    };
    expect(parsed.source).toBe("meeting_note");
    expect(parsed.content).toEqual({ text: "Calibration walkthrough." });
    expect(onChanged).toHaveBeenCalled();
  });

  it("posts a parsed JSON object when the body parses", async () => {
    const calls: Call[] = [];
    vi.stubGlobal("fetch", recordingFetch(calls));
    const user = userEvent.setup();
    render(<InteractionImport engagementId="e1" />);

    // user.type treats `{` and `[` as special-key escapes; use fireEvent for
    // raw JSON. Click the button via userEvent so the submit handler runs.
    fireEvent.change(screen.getByLabelText("Content (text or JSON)"), {
      target: { value: '{"subject":"Calibration","participants":["dot@nyc.gov"]}' },
    });
    await user.click(screen.getByRole("button", { name: "Import" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const posted = calls.find((c) => c.method === "POST")!;
    const parsed = JSON.parse(posted.body) as { content: Record<string, unknown> };
    expect(parsed.content).toEqual({
      subject: "Calibration",
      participants: ["dot@nyc.gov"],
    });
  });
});
