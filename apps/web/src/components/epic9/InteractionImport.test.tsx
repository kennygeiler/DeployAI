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

  it("posts a meeting_note paste through the meeting-notes parser", async () => {
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
    // Plain-text meeting note → text + format="plain" (no Otter/Granola markers).
    expect(parsed.content.text).toBe("Calibration walkthrough.");
    expect(parsed.content.format).toBe("plain");
    expect(onChanged).toHaveBeenCalled();
  });

  // --- Phase 6.3.1 / 6.3.2 — paste-parser routing ---------------------------

  it("parses an email paste and surfaces headers + occurred_at", async () => {
    const calls: Call[] = [];
    vi.stubGlobal("fetch", recordingFetch(calls));
    const user = userEvent.setup();
    render(<InteractionImport engagementId="e1" />);

    await user.selectOptions(screen.getByLabelText("Source"), "email");
    const rawEmail =
      "From: Dana Carter <dana@acme.gov>\n" +
      "To: Priya <priya@acme.gov>\n" +
      "Subject: Pilot scope\n" +
      "Date: 2026-03-23T15:00:00Z\n" +
      "\n" +
      "Confirming the 90-day scope.";
    fireEvent.change(screen.getByLabelText("Content (text or JSON)"), {
      target: { value: rawEmail },
    });
    await user.click(screen.getByRole("button", { name: "Import" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const posted = calls.find((c) => c.method === "POST")!;
    const body = JSON.parse(posted.body) as {
      source: string;
      content: Record<string, unknown>;
      occurred_at?: string;
    };
    expect(body.source).toBe("email");
    expect(body.content.subject).toBe("Pilot scope");
    expect(body.content.from).toBe("Dana Carter <dana@acme.gov>");
    expect(body.content.text).toBe("Confirming the 90-day scope.");
    expect(body.occurred_at).toBe("2026-03-23T15:00:00.000Z");
  });

  it("parses an Otter-style meeting-note paste and pulls out participants", async () => {
    const calls: Call[] = [];
    vi.stubGlobal("fetch", recordingFetch(calls));
    const user = userEvent.setup();
    render(<InteractionImport engagementId="e1" />);

    await user.selectOptions(screen.getByLabelText("Source"), "meeting_note");
    const transcript =
      "[Dana Carter 00:00:01] Welcome.\n" +
      "[Priya Raman 00:00:14] Thanks.\n" +
      "[Marcus Okafor 00:01:02] Quick vendor update.";
    fireEvent.change(screen.getByLabelText("Content (text or JSON)"), {
      target: { value: transcript },
    });
    await user.click(screen.getByRole("button", { name: "Import" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const posted = calls.find((c) => c.method === "POST")!;
    const body = JSON.parse(posted.body) as {
      content: { format?: string; participants?: string[]; text?: string };
    };
    expect(body.content.format).toBe("otter");
    expect(body.content.participants?.sort()).toEqual([
      "Dana Carter",
      "Marcus Okafor",
      "Priya Raman",
    ]);
    expect(body.content.text).toContain("Dana Carter: Welcome.");
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
