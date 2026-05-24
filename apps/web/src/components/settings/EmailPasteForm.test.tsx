import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EmailPasteForm } from "./EmailPasteForm.client";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

type Call = { url: string; method: string; body?: unknown };

function mockFetch(handler: (body: unknown) => { ok: boolean; status?: number; json: unknown }): {
  calls: Call[];
} {
  const calls: Call[] = [];
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
    const method = init?.method ?? "GET";
    const parsedBody = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({ url, method, body: parsedBody });
    const out = handler(parsedBody);
    return Promise.resolve({
      ok: out.ok,
      status: out.status ?? (out.ok ? 201 : 400),
      json: () => Promise.resolve(out.json),
      text: () =>
        Promise.resolve(typeof out.json === "string" ? out.json : JSON.stringify(out.json)),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls };
}

describe("EmailPasteForm", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("renders all three source options and a textarea", () => {
    render(<EmailPasteForm />);
    const select = screen.getByLabelText("Source") as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((o) => o.value);
    expect(optionValues).toEqual(["imap_paste", "mbox_paste", "manual_paste"]);
    expect(screen.getByLabelText("Raw message")).toBeTruthy();
  });

  it("posts source + raw to the BFF on submit and shows the imported count", async () => {
    const { calls } = mockFetch(() => ({
      ok: true,
      status: 201,
      json: {
        events: [
          {
            id: "11111111-1111-1111-1111-111111111111",
            tenant_id: "22222222-2222-2222-2222-222222222222",
            engagement_id: null,
            source: "imap_paste",
            external_message_id: "<abc@x>",
            raw_payload: "body",
            parsed_subject: "subj",
            parsed_from: "a@x.com",
            parsed_to: ["b@x.com"],
            parsed_date: null,
            received_at: "2026-05-24T10:00:00Z",
            processed_at: null,
            error: null,
          },
        ],
      },
    }));
    render(<EmailPasteForm />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Raw message"), "Subject: hi\n\nbody");
    await user.click(screen.getByRole("button", { name: /import/i }));
    await waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0]!.url).toBe("/api/bff/tenant/emails/ingest");
    expect(calls[0]!.method).toBe("POST");
    expect(calls[0]!.body).toEqual({ source: "imap_paste", raw: "Subject: hi\n\nbody" });
    await waitFor(() =>
      expect(screen.getByText(/Imported 1 message on the most recent submit/)).toBeTruthy(),
    );
  });

  it("sends the selected source when switched to mbox_paste", async () => {
    const { calls } = mockFetch(() => ({
      ok: true,
      status: 201,
      json: {
        events: [
          {
            id: "11111111-1111-1111-1111-111111111111",
            tenant_id: "22222222-2222-2222-2222-222222222222",
            engagement_id: null,
            source: "mbox_paste",
            external_message_id: "<a@x>",
            raw_payload: "body",
            parsed_subject: "a",
            parsed_from: "a@x.com",
            parsed_to: [],
            parsed_date: null,
            received_at: "2026-05-24T10:00:00Z",
            processed_at: null,
            error: null,
          },
          {
            id: "33333333-3333-3333-3333-333333333333",
            tenant_id: "22222222-2222-2222-2222-222222222222",
            engagement_id: null,
            source: "mbox_paste",
            external_message_id: "<b@x>",
            raw_payload: "body",
            parsed_subject: "b",
            parsed_from: "a@x.com",
            parsed_to: [],
            parsed_date: null,
            received_at: "2026-05-24T10:00:00Z",
            processed_at: null,
            error: null,
          },
        ],
      },
    }));
    render(<EmailPasteForm />);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Source"), "mbox_paste");
    await user.type(screen.getByLabelText("Raw message"), "From a@x.com Mon ...");
    await user.click(screen.getByRole("button", { name: /import/i }));
    await waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0]!.body).toMatchObject({ source: "mbox_paste" });
    await waitFor(() => expect(screen.getByText(/Imported 2 messages/)).toBeTruthy());
  });

  it("renders an error message when the BFF rejects", async () => {
    mockFetch(() => ({ ok: false, status: 400, json: "Bad Request: invalid source" }));
    render(<EmailPasteForm />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Raw message"), "Subject: hi\n\nbody");
    await user.click(screen.getByRole("button", { name: /import/i }));
    await waitFor(() => expect(screen.getByText(/Bad Request: invalid source/)).toBeTruthy());
  });
});
